#!/usr/bin/env python3
"""
Baseline diff engine for UI regression testing.

Compares current test results against a saved baseline to detect regressions.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class BaselineDiff:
    """Compare current test results against a saved baseline."""

    def __init__(
        self,
        current_ocr: Dict,
        current_a11y: List[Dict],
        baseline_data: Dict,
        threshold: float = 0.1,
        image_size: Optional[Tuple[int, int]] = None,
    ):
        self.current_ocr_texts = {
            t["text"] for t in current_ocr.get("texts", []) if t.get("text")
        }
        self.current_a11y_texts = {
            e["text"] for e in current_a11y if e.get("text")
        }
        self.baseline_ocr_texts = {
            t["text"] for t in baseline_data.get("ocr_texts", []) if t.get("text")
        }
        self.baseline_a11y_texts = {
            e["text"] for e in baseline_data.get("a11y_elements", []) if e.get("text")
        }
        self.baseline_ocr_map = {
            t["text"]: t for t in baseline_data.get("ocr_texts", []) if t.get("text")
        }
        self.current_ocr_map = {
            t["text"]: t for t in current_ocr.get("texts", []) if t.get("text")
        }
        self.threshold = threshold
        self.image_size = image_size or tuple(baseline_data.get("image_size", [1280, 720]))
        self.results: List[Dict[str, Any]] = []

    def run(self) -> List[Dict[str, Any]]:
        """Execute all baseline diff checks."""
        self._check_removed_texts()
        self._check_added_texts()
        self._check_layout_shifts()
        self._check_element_count_changes()
        self._check_a11y_regressions()
        return self.results

    def _check_removed_texts(self):
        """Text that existed in baseline but is now missing."""
        removed = self.baseline_ocr_texts - self.current_ocr_texts
        for text in list(removed)[:10]:
            self.results.append({
                "type": "baseline_regression",
                "subtype": "text_removed",
                "level": "L1",
                "severity": "error",
                "element": text[:60],
                "expected": f"Text exists in baseline: '{text}'",
                "actual": "Not found in current run",
                "suggestion": "Regression: text that was previously visible is now missing",
            })

    def _check_added_texts(self):
        """New text not present in baseline."""
        added = self.current_ocr_texts - self.baseline_ocr_texts
        for text in list(added)[:10]:
            self.results.append({
                "type": "baseline_regression",
                "subtype": "text_added",
                "level": "L1",
                "severity": "warning",
                "element": text[:60],
                "expected": "No unexpected text",
                "actual": f"New text: '{text}'",
                "suggestion": "Unexpected content appeared - verify if intentional",
            })

    def _check_layout_shifts(self):
        """Detect position changes for the same text."""
        for text in self.current_ocr_texts & self.baseline_ocr_texts:
            old_item = self.baseline_ocr_map.get(text)
            new_item = self.current_ocr_map.get(text)
            if not old_item or not new_item:
                continue
            old_box = old_item.get("box", [])
            new_box = new_item.get("box", [])
            if len(old_box) != 4 or len(new_box) != 4:
                continue

            shift = self._calculate_shift(old_box, new_box)
            max_dim = max(self.image_size)
            if shift > self.threshold * max_dim:
                self.results.append({
                    "type": "baseline_regression",
                    "subtype": "layout_shift",
                    "level": "L2",
                    "severity": "warning",
                    "element": text[:60],
                    "expected": f"Position: {old_box}",
                    "actual": f"Position: {new_box} (shift: {shift:.0f}px)",
                    "screenshot_region": new_box,
                    "suggestion": "Layout shift detected - element moved significantly",
                })

    def _check_element_count_changes(self):
        """Significant change in text element count."""
        old_count = len(self.baseline_ocr_texts)
        new_count = len(self.current_ocr_texts)
        if old_count > 0:
            delta = abs(new_count - old_count) / old_count
            if delta > self.threshold:
                self.results.append({
                    "type": "baseline_regression",
                    "subtype": "count_change",
                    "level": "L3",
                    "severity": "warning",
                    "element": "page",
                    "expected": f"~{old_count} text elements",
                    "actual": f"{new_count} text elements (change: {delta:.0%})",
                    "suggestion": "Significant change in text element count",
                })

    def _check_a11y_regressions(self):
        """A11y elements that disappeared."""
        removed_a11y = self.baseline_a11y_texts - self.current_a11y_texts
        for text in list(removed_a11y)[:5]:
            self.results.append({
                "type": "baseline_regression",
                "subtype": "a11y_element_removed",
                "level": "L4",
                "severity": "error",
                "element": text[:60],
                "expected": f"A11y element exists in baseline: '{text}'",
                "actual": "Not found in current accessibility tree",
                "suggestion": "Accessibility regression: element lost its accessible name",
            })

    @staticmethod
    def _calculate_shift(box1: List, box2: List) -> float:
        """Calculate pixel distance between two box centers."""
        cx1 = sum(p[0] for p in box1) / 4
        cy1 = sum(p[1] for p in box1) / 4
        cx2 = sum(p[0] for p in box2) / 4
        cy2 = sum(p[1] for p in box2) / 4
        return ((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2) ** 0.5


def create_baseline(
    ocr_result: Dict,
    a11y_elements: List[Dict],
    url: str,
    viewport: str,
    image_size: Tuple[int, int],
    summary: Dict,
) -> Dict:
    """Create a baseline data structure from current test run."""
    return {
        "baseline_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "viewport": viewport,
        "image_size": list(image_size),
        "ocr_texts": ocr_result.get("texts", []),
        "a11y_elements": a11y_elements,
        "summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Baseline diff for UI regression testing")
    parser.add_argument("--baseline", required=True, help="Path to baseline JSON file")
    parser.add_argument("--current-report", required=True, help="Path to current report.json")
    parser.add_argument("--threshold", type=float, default=0.1, help="Layout shift threshold (ratio of max dimension)")
    parser.add_argument("--output", default=None, help="Output diff report path")
    args = parser.parse_args()

    baseline_data = json.loads(Path(args.baseline).read_text())
    current_report = json.loads(Path(args.current_report).read_text())

    ocr_result = {"texts": []}
    for r in current_report.get("results", []):
        if r.get("screenshot_region"):
            ocr_result["texts"].append({"text": r.get("element", ""), "box": r["screenshot_region"]})

    diff = BaselineDiff(
        current_ocr=ocr_result,
        current_a11y=[],
        baseline_data=baseline_data,
        threshold=args.threshold,
    )
    results = diff.run()

    output_data = {
        "diff_timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_file": args.baseline,
        "current_report": args.current_report,
        "threshold": args.threshold,
        "summary": {
            "total_issues": len(results),
            "errors": sum(1 for r in results if r["severity"] == "error"),
            "warnings": sum(1 for r in results if r["severity"] == "warning"),
        },
        "issues": results,
    }

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(args.baseline).parent / "diff.json"

    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    print(f"Diff report saved: {output_path}")
    print(f"  {output_data['summary']['total_issues']} issues: "
          f"{output_data['summary']['errors']} errors, "
          f"{output_data['summary']['warnings']} warnings")


if __name__ == "__main__":
    main()
