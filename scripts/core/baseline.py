from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import Issue, coerce_issues


class BaselineDiff:
    """Compare current test results against a saved baseline."""

    def __init__(
        self,
        current_ocr: Dict[str, Any],
        current_a11y: List[Dict[str, Any]],
        baseline_data: Dict[str, Any],
        threshold: float = 0.1,
        image_size: Optional[Tuple[int, int]] = None,
    ):
        self.current_ocr_texts = {
            t["text"] for t in current_ocr.get("texts", []) if t.get("text")
        }
        self.current_a11y_texts = {e["text"] for e in current_a11y if e.get("text")}
        self.baseline_ocr_texts = {
            t["text"]
            for t in baseline_data.get("ocr_texts", [])
            if isinstance(t, dict) and t.get("text")
        }
        self.baseline_a11y_texts = {
            e["text"]
            for e in baseline_data.get("a11y_elements", [])
            if isinstance(e, dict) and e.get("text")
        }
        self.baseline_ocr_map = {
            t["text"]: t
            for t in baseline_data.get("ocr_texts", [])
            if isinstance(t, dict) and t.get("text")
        }
        self.current_ocr_map = {
            t["text"]: t for t in current_ocr.get("texts", []) if t.get("text")
        }
        self.threshold = threshold
        self.image_size = image_size or tuple(
            baseline_data.get("image_size", [1280, 720])
        )
        self.results: List[Issue] = []

    def run(self) -> List[Dict[str, Any]]:
        self._check_removed_texts()
        self._check_added_texts()
        self._check_layout_shifts()
        self._check_element_count_changes()
        self._check_a11y_regressions()
        return coerce_issues(self.results)

    def _check_removed_texts(self) -> None:
        removed = self.baseline_ocr_texts - self.current_ocr_texts
        for text in list(removed)[:10]:
            self.results.append(
                Issue(
                    type="baseline_regression",
                    level="L1",
                    severity="error",
                    element=text[:60],
                    expected=f"Text exists in baseline: '{text}'",
                    actual="Not found in current run",
                    suggestion=(
                        "Regression: text that was previously visible is now missing"
                    ),
                    meta={"subtype": "text_removed"},
                )
            )

    def _check_added_texts(self) -> None:
        added = self.current_ocr_texts - self.baseline_ocr_texts
        for text in list(added)[:10]:
            self.results.append(
                Issue(
                    type="baseline_regression",
                    level="L1",
                    severity="warning",
                    element=text[:60],
                    expected="No unexpected text",
                    actual=f"New text: '{text}'",
                    suggestion="Unexpected content appeared - verify if intentional",
                    meta={"subtype": "text_added"},
                )
            )

    def _check_layout_shifts(self) -> None:
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
                self.results.append(
                    Issue(
                        type="baseline_regression",
                        level="L2",
                        severity="warning",
                        element=text[:60],
                        expected=f"Position: {old_box}",
                        actual=f"Position: {new_box} (shift: {shift:.0f}px)",
                        screenshot_region=new_box,
                        suggestion="Layout shift detected - element moved significantly",
                        meta={"subtype": "layout_shift"},
                    )
                )

    def _check_element_count_changes(self) -> None:
        old_count = len(self.baseline_ocr_texts)
        new_count = len(self.current_ocr_texts)
        if old_count > 0:
            delta = abs(new_count - old_count) / old_count
            if delta > self.threshold:
                self.results.append(
                    Issue(
                        type="baseline_regression",
                        level="L3",
                        severity="warning",
                        element="page",
                        expected=f"~{old_count} text elements",
                        actual=f"{new_count} text elements (change: {delta:.0%})",
                        suggestion="Significant change in text element count",
                        meta={"subtype": "count_change"},
                    )
                )

    def _check_a11y_regressions(self) -> None:
        removed_a11y = self.baseline_a11y_texts - self.current_a11y_texts
        for text in list(removed_a11y)[:5]:
            self.results.append(
                Issue(
                    type="baseline_regression",
                    level="L4",
                    severity="error",
                    element=text[:60],
                    expected=f"A11y element exists in baseline: '{text}'",
                    actual="Not found in current accessibility tree",
                    suggestion=(
                        "Accessibility regression: element lost its accessible name"
                    ),
                    meta={"subtype": "a11y_element_removed"},
                )
            )

    @staticmethod
    def _calculate_shift(box1: List[List[int]], box2: List[List[int]]) -> float:
        cx1 = sum(point[0] for point in box1) / 4
        cy1 = sum(point[1] for point in box1) / 4
        cx2 = sum(point[0] for point in box2) / 4
        cy2 = sum(point[1] for point in box2) / 4
        return ((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2) ** 0.5


def create_baseline(
    ocr_result: Dict[str, Any],
    a11y_elements: List[Dict[str, Any]],
    url: str,
    viewport: str,
    image_size: Tuple[int, int],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "baseline_version": "1.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "viewport": viewport,
        "image_size": list(image_size),
        "ocr_texts": ocr_result.get("texts", []),
        "a11y_elements": a11y_elements,
        "summary": summary,
    }
