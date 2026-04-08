from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from adapters.registry import build_adapter
from core.a11y import flatten_a11y_tree
from core.baseline import BaselineDiff, create_baseline
from core.models import DetectionContext, EvidenceBundle
from core.reporting import ReportWriter
from providers.ocr import create_ocr_provider


@dataclass
class CollectedEvidence:
    bundle: EvidenceBundle
    input_mode: str
    screenshot_path: Path
    after_capture_path: Optional[str]
    a11y_elements: List[Dict[str, Any]]
    image_size: Tuple[int, int]


@dataclass
class OCRArtifacts:
    ocr_result: Dict[str, Any]
    before_ocr: Optional[Dict[str, Any]] = None
    after_ocr: Optional[Dict[str, Any]] = None


def _copy_screenshot_to_output(source_path: Path, output_dir: Path) -> Path:
    output_path = output_dir / "screenshot.png"
    if source_path.resolve() != output_path.resolve():
        output_path.write_bytes(source_path.read_bytes())
    return output_path


async def collect_evidence(
    args: Any,
    *,
    viewport: str,
    wait_ms: int,
    output_dir: Path,
    enable_actions: bool = False,
) -> CollectedEvidence:
    adapter, input_mode = build_adapter(args)
    if input_mode == "url":
        if not args.url:
            raise ValueError("--url is required when input mode is 'url'")
        from adapters.standalone_url import capture_from_url

        requested_screenshot = output_dir / "screenshot.png"
        after_screenshot_path = output_dir / "screenshot_after.png"
        bundle, after_capture_path = await capture_from_url(
            url=args.url,
            viewport=viewport,
            wait_ms=wait_ms,
            screenshot_path=requested_screenshot,
            source=args.source or "standalone",
            actions=args.actions if enable_actions and args.actions else None,
            after_screenshot_path=after_screenshot_path,
        )
    else:
        bundle = await adapter.load_bundle()
        after_capture_path = None

    screenshot_path = _copy_screenshot_to_output(
        Path(bundle.screenshot_path),
        output_dir,
    )
    bundle.screenshot_path = str(screenshot_path)

    if getattr(args, "source_map", None):
        bundle.capabilities["has_source_map"] = True
        bundle.extras["source_map"] = args.source_map
        bundle.provenance["source_map"] = args.source_map

    a11y_elements = flatten_a11y_tree(bundle.a11y_tree or {}, leaf_only=True)
    with Image.open(screenshot_path) as image:
        image_size = image.size

    return CollectedEvidence(
        bundle=bundle,
        input_mode=input_mode,
        screenshot_path=screenshot_path,
        after_capture_path=after_capture_path,
        a11y_elements=a11y_elements,
        image_size=image_size,
    )


async def run_ocr_stage(
    args: Any,
    *,
    api_key: str,
    collected: CollectedEvidence,
    run_action_ocr: bool = False,
) -> OCRArtifacts:
    ocr_provider = create_ocr_provider(args.ocr_provider, api_key=api_key)
    print(
        f"Sending screenshot to {args.ocr_provider} "
        f"({collected.image_size[0]}x{collected.image_size[1]}) ..."
    )
    ocr_result = await ocr_provider.recognize(str(collected.screenshot_path))

    before_ocr = None
    after_ocr = None
    if (
        run_action_ocr
        and collected.bundle.capabilities.get("has_actions")
        and collected.after_capture_path
    ):
        before_ocr = ocr_result
        print("Running after-action OCR ...")
        after_ocr = await ocr_provider.recognize(collected.after_capture_path)

    return OCRArtifacts(
        ocr_result=ocr_result,
        before_ocr=before_ocr,
        after_ocr=after_ocr,
    )


def build_detection_context(
    *,
    settings: Any,
    collected: CollectedEvidence,
    ocr_artifacts: OCRArtifacts,
) -> DetectionContext:
    return DetectionContext(
        ocr_result=ocr_artifacts.ocr_result,
        a11y_elements=collected.a11y_elements,
        config=settings.config,
        image_size=collected.image_size,
        rules=settings.rules,
        evidence=collected.bundle,
        before_ocr=ocr_artifacts.before_ocr,
        after_ocr=ocr_artifacts.after_ocr,
    )


def apply_baseline_stage(
    args: Any,
    *,
    output_dir: Path,
    collected: CollectedEvidence,
    ocr_artifacts: OCRArtifacts,
    viewport: str,
    summary: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if args.baseline:
        baseline_data = create_baseline(
            ocr_result=ocr_artifacts.ocr_result,
            a11y_elements=collected.a11y_elements,
            url=collected.bundle.url or args.url or "",
            viewport=collected.bundle.viewport or viewport,
            image_size=collected.image_size,
            summary=summary,
        )
        baseline_path = output_dir / "baseline.json"
        baseline_path.write_text(
            json.dumps(baseline_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Baseline saved: {baseline_path}")

    if not args.baseline_file:
        return results

    baseline_data = json.loads(Path(args.baseline_file).read_text(encoding="utf-8"))
    diff_engine = BaselineDiff(
        current_ocr=ocr_artifacts.ocr_result,
        current_a11y=collected.a11y_elements,
        baseline_data=baseline_data,
        threshold=args.diff_threshold,
        image_size=collected.image_size,
    )
    diff_results = diff_engine.run()
    print(f"  Baseline diff: {len(diff_results)} issues found")
    return [*results, *diff_results]


def enrich_findings(
    results: List[Dict[str, Any]],
    *,
    a11y_elements: List[Dict[str, Any]],
    source_map_dir: Optional[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not source_map_dir:
        return results, {"status": "skipped", "reason": "no source map directory"}
    if not a11y_elements:
        return results, {
            "status": "skipped",
            "reason": "missing required capabilities",
            "missing_capabilities": ["has_a11y"],
        }

    from source_map_lookup import resolve_issues

    enriched = resolve_issues([dict(issue) for issue in results], a11y_elements, source_map_dir)
    return enriched, {"status": "executed", "source_map_dir": source_map_dir}


def write_output_stage(
    args: Any,
    *,
    collected: CollectedEvidence,
    ocr_artifacts: OCRArtifacts,
    results: List[Dict[str, Any]],
    duration: float,
    profile_name: str,
    levels: List[str],
    detector_execution: List[Dict[str, Any]],
    source_map_execution: Dict[str, Any],
) -> tuple[ReportWriter, Dict[str, str]]:
    reporter = ReportWriter(
        url=collected.bundle.url or args.url or "(external artifact)",
        results=results,
        output_dir=args.output,
        image_size=collected.image_size,
        duration=duration,
        metadata={
            "input_mode": collected.input_mode,
            "source": collected.bundle.source,
            "profile": profile_name,
            "levels": levels,
            "ocr_provider": args.ocr_provider,
            "capabilities": collected.bundle.capabilities,
            "provenance": collected.bundle.provenance,
            "detector_execution": detector_execution,
            "source_map_execution": source_map_execution,
        },
        snapshots={
            "ocr_texts": ocr_artifacts.ocr_result.get("texts", []),
            "a11y_elements": collected.a11y_elements,
        },
    )
    return reporter, reporter.write_selected(args.format)
