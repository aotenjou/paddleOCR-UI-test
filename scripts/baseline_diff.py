#!/usr/bin/env python3
"""Baseline diff engine for UI regression testing."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.baseline import BaselineDiff


def _load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _extract_current_snapshots(current_report: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    snapshots = current_report.get("snapshots", {})
    ocr_texts = snapshots.get("ocr_texts")
    a11y_elements = snapshots.get("a11y_elements")

    if ocr_texts is None:
        ocr_texts = []
        for result in current_report.get("results", []):
            if result.get("screenshot_region"):
                ocr_texts.append(
                    {
                        "text": result.get("element", ""),
                        "box": result["screenshot_region"],
                    }
                )

    if a11y_elements is None:
        a11y_elements = []

    return {"texts": ocr_texts}, a11y_elements


def _normalize_baseline_data(baseline_payload: Dict[str, Any]) -> Dict[str, Any]:
    if "ocr_texts" in baseline_payload or "a11y_elements" in baseline_payload:
        return baseline_payload

    extracted_ocr, extracted_a11y = _extract_current_snapshots(baseline_payload)
    normalized = dict(baseline_payload)
    normalized["ocr_texts"] = extracted_ocr.get("texts", [])
    normalized["a11y_elements"] = extracted_a11y
    normalized.setdefault("image_size", baseline_payload.get("image_size", [1280, 720]))
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline diff for UI regression testing")
    parser.add_argument("--baseline", required=True, help="Path to baseline JSON file")
    parser.add_argument("--current-report", required=True, help="Path to current report.json")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Layout shift threshold (ratio of max dimension)",
    )
    parser.add_argument("--output", default=None, help="Output diff report path")
    args = parser.parse_args()

    baseline_data = _normalize_baseline_data(_load_json(args.baseline))
    current_report = _load_json(args.current_report)
    current_ocr, current_a11y = _extract_current_snapshots(current_report)

    diff = BaselineDiff(
        current_ocr=current_ocr,
        current_a11y=current_a11y,
        baseline_data=baseline_data,
        threshold=args.threshold,
    )
    results = diff.run()

    output_data = {
        "schema_version": "1.1",
        "diff_timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_file": args.baseline,
        "current_report": args.current_report,
        "threshold": args.threshold,
        "summary": {
            "total_issues": len(results),
            "errors": sum(1 for result in results if result.get("severity") == "error"),
            "warnings": sum(1 for result in results if result.get("severity") == "warning"),
        },
        "issues": results,
    }

    output_path = Path(args.output) if args.output else Path(args.baseline).parent / "diff.json"
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Diff report saved: {output_path}")
    print(
        f"  {output_data['summary']['total_issues']} issues: "
        f"{output_data['summary']['errors']} errors, "
        f"{output_data['summary']['warnings']} warnings"
    )


if __name__ == "__main__":
    main()
