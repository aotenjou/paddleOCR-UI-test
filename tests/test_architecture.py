from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from core.baseline import BaselineDiff
from core.config import load_rules, load_runtime_config, resolve_run_settings
from core.models import DetectionContext
from core.reporting import ReportWriter
from baseline_diff import _normalize_baseline_data
from engines.registry import execute_levels, list_detectors, run_levels


class ArchitectureTests(unittest.TestCase):
    def test_resolve_run_settings_merges_profile_configuration(self) -> None:
        rules = load_rules()
        args = SimpleNamespace(levels=None, viewport=None, wait=2000)
        profile = {
            "default_levels": ["L3"],
            "viewport": "1280x720",
            "wait_ms": 3500,
            "ignore_patterns": [r"^v\\d+"],
            "expected_elements": [{"role": "navigation", "min_count": 1}],
            "rule_overrides": {
                "dom-ocr-crossval.count_mismatch.delta_threshold": 0.1,
            },
        }
        raw_config = {
            "ignore_patterns": [r"^hash$"],
            "expected_elements": [{"role": "button", "min_count": 1}],
        }

        settings = resolve_run_settings(
            args=args,
            raw_config=raw_config,
            rules=rules,
            profile=profile,
        )

        self.assertEqual(settings.levels, ["L3"])
        self.assertEqual(settings.viewport, "1280x720")
        self.assertEqual(settings.wait_ms, 3500)
        self.assertEqual(
            settings.rules["dom-ocr-crossval"]["count_mismatch"]["delta_threshold"],
            0.1,
        )
        self.assertEqual(len(settings.config["expected_elements"]), 2)
        self.assertIn(r"^v\\d+", settings.rules["text-consistency"]["ignore_patterns"])
        self.assertIn(r"^hash$", settings.rules["dom-ocr-crossval"]["ignore_patterns"])

    def test_l3_detector_enforces_expected_elements(self) -> None:
        context = DetectionContext(
            ocr_result={"texts": [{"text": "Checkout", "box": []}]},
            a11y_elements=[
                {"role": "button", "text": "Checkout", "bounds": {}, "path": "root[0]"}
            ],
            config={"expected_elements": [{"role": "navigation", "min_count": 1}]},
            image_size=(1280, 720),
            rules=load_rules(),
        )

        results = run_levels(["L3"], context)
        self.assertIn("expected_element_missing", {result["type"] for result in results})

    def test_runtime_config_rejects_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "invalid-config.json"
            config_path.write_text(
                json.dumps({"expected_texts": {}, "unknown_key": True}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_runtime_config(str(config_path))

    def test_execute_levels_skips_missing_capabilities(self) -> None:
        context = DetectionContext(
            ocr_result={"texts": [{"text": "Login", "box": []}]},
            a11y_elements=[],
            config={},
            image_size=(1280, 720),
            rules=load_rules(),
        )

        outcome = execute_levels(["L4"], context)

        self.assertEqual(outcome.issues, [])
        self.assertEqual(len(outcome.execution), 1)
        self.assertEqual(outcome.execution[0]["status"], "skipped")
        self.assertIn("has_a11y", outcome.execution[0]["missing_capabilities"])

    def test_detector_registry_exposes_descriptors(self) -> None:
        descriptors = list_detectors(detailed=True)

        self.assertTrue(descriptors)
        self.assertIn("level", descriptors[0])
        self.assertIn("required_capabilities", descriptors[0])

    def test_report_writer_generates_all_formats(self) -> None:
        results = [
            {
                "type": "text_missing",
                "level": "L1",
                "severity": "error",
                "element": "submit_button",
                "expected": "Submit",
                "actual": "Not found",
                "source_location": {"file": "src/app.tsx", "line": 12},
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ReportWriter(
                url="https://example.com",
                results=results,
                output_dir=tmpdir,
                image_size=(1280, 720),
                duration=1.2,
                metadata={"input_mode": "artifacts"},
                snapshots={"ocr_texts": [{"text": "Submit", "box": []}]},
            )
            outputs = writer.write_selected("all")

            self.assertTrue(Path(outputs["json"]).exists())
            self.assertTrue(Path(outputs["markdown"]).exists())
            self.assertTrue(Path(outputs["junit"]).exists())
            self.assertTrue(Path(outputs["sarif"]).exists())

            payload = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["input_mode"], "artifacts")
            self.assertIn("ocr_texts", payload["snapshots"])

    def test_baseline_diff_uses_snapshot_style_payloads(self) -> None:
        baseline_data = {
            "ocr_texts": [{"text": "Login", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
            "a11y_elements": [{"text": "Login"}],
            "image_size": [1280, 720],
        }
        diff = BaselineDiff(
            current_ocr={"texts": [{"text": "Login", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}]},
            current_a11y=[{"text": "Login"}],
            baseline_data=baseline_data,
            threshold=0.1,
        )
        self.assertEqual(diff.run(), [])

    def test_baseline_normalization_accepts_report_payload(self) -> None:
        payload = {
            "snapshots": {
                "ocr_texts": [{"text": "Login", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
                "a11y_elements": [{"text": "Login"}],
            },
            "image_size": [1280, 720],
        }

        normalized = _normalize_baseline_data(payload)

        self.assertIn("ocr_texts", normalized)
        self.assertIn("a11y_elements", normalized)
        self.assertEqual(len(normalized["ocr_texts"]), 1)


if __name__ == "__main__":
    unittest.main()
