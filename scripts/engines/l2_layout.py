from __future__ import annotations

from typing import Dict, List, Sequence

from core.models import DetectionContext, Issue

from .base import BaseLevelDetector


class LayoutReasonablenessDetector(BaseLevelDetector):
    level = "L2"
    name = "layout_reasonableness"
    description = "Detect overflow, overlap, truncation, and touch target issues."
    optional_capabilities = ("has_a11y",)

    def run(self, context: DetectionContext) -> List[Issue]:
        rules = context.rules.get("layout-anomaly", {})
        img_w, img_h = context.image_size
        issues: List[Issue] = []

        for index, item in enumerate(context.ocr_result.get("texts", [])):
            box = item.get("box", [])
            if len(box) != 4:
                continue
            x_coords = [point[0] for point in box]
            y_coords = [point[1] for point in box]
            x_min, x_max = min(x_coords), max(x_coords)
            y_min, y_max = min(y_coords), max(y_coords)
            width = x_max - x_min
            height = y_max - y_min

            if rules.get("overflow", {}).get("enabled", True):
                if x_min < 0 or y_min < 0 or x_max > img_w or y_max > img_h:
                    issues.append(
                        self.issue(
                            issue_type="overflow",
                            severity=rules.get("overflow", {}).get("severity", "warning"),
                            element=f"text_region_{index}",
                            expected=f"within {img_w}x{img_h}",
                            actual=f"extends to ({x_min}, {y_min})-({x_max}, {y_max})",
                            screenshot_region=box,
                            suggestion="Check container overflow settings or viewport size",
                        )
                    )

            full_page = rules.get("full_page_text", {})
            if full_page.get("enabled", True):
                if width > img_w * full_page.get("width_threshold", 0.95) and height > img_h * full_page.get("height_threshold", 0.8):
                    issues.append(
                        self.issue(
                            issue_type="possible_full_page_text",
                            severity=full_page.get("severity", "warning"),
                            element=f"text_region_{index}",
                            expected="normal text block",
                            actual=f"spans {width}x{height} ({width / img_w * 100:.0f}% width)",
                            screenshot_region=box,
                            suggestion="Verify this is not a rendering artifact",
                        )
                    )

            truncation = rules.get("text_truncation", {})
            text_value = item.get("text", "")
            if truncation.get("enabled", False) and (text_value.endswith("...") or text_value.endswith("…")):
                if len(text_value) >= truncation.get("min_expected_chars", 20):
                    issues.append(
                        self.issue(
                            issue_type="text_truncation",
                            severity=truncation.get("severity", "warning"),
                            element=text_value[:40],
                            expected="fully visible text",
                            actual=f"OCR detected truncated text: {text_value}",
                            screenshot_region=box,
                            suggestion="Check width constraints or overflow handling",
                        )
                    )

        if rules.get("element_overlap", {}).get("enabled", False):
            issues.extend(self._check_element_overlap(context.ocr_result.get("texts", []), rules.get("element_overlap", {})))
        if rules.get("touch_target_size", {}).get("enabled", False):
            issues.extend(self._check_touch_targets(context, rules.get("touch_target_size", {})))

        return issues

    def _check_element_overlap(self, ocr_texts: Sequence[Dict], config: Dict) -> List[Issue]:
        threshold = config.get("iou_threshold", 0.3)
        boxes = []
        for item in ocr_texts:
            box = item.get("box", [])
            if len(box) == 4:
                boxes.append((item.get("text", ""), box))

        issues: List[Issue] = []
        for left in range(len(boxes)):
            for right in range(left + 1, len(boxes)):
                iou = self._calculate_iou(boxes[left][1], boxes[right][1])
                if iou > threshold:
                    issues.append(
                        self.issue(
                            issue_type="element_overlap",
                            severity=config.get("severity", "warning"),
                            element=f"{boxes[left][0][:30]} / {boxes[right][0][:30]}",
                            expected="No overlapping text regions",
                            actual=f"IoU: {iou:.2f} (threshold: {threshold})",
                            screenshot_region=boxes[left][1],
                            suggestion="Check for overlapping elements or z-index issues",
                        )
                    )
        return issues

    def _check_touch_targets(self, context: DetectionContext, config: Dict) -> List[Issue]:
        min_w = config.get("min_width_px", 44)
        min_h = config.get("min_height_px", 44)
        interactive_roles = {"button", "link", "combobox", "tab"}
        issues: List[Issue] = []
        for element in context.a11y_elements:
            if element.get("role") not in interactive_roles:
                continue
            bounds = element.get("bounds", {})
            width, height = bounds.get("width", 0), bounds.get("height", 0)
            if (width > 0 and width < min_w) or (height > 0 and height < min_h):
                issues.append(
                    self.issue(
                        issue_type="touch_target_too_small",
                        severity=config.get("severity", "warning"),
                        element=f"{element.get('role')}: {element.get('text', '')[:30]}",
                        expected=f">= {min_w}x{min_h}px",
                        actual=f"{width}x{height}px",
                        suggestion="Increase touch target size (min 44x44px for accessibility)",
                    )
                )
        return issues

    @staticmethod
    def _calculate_iou(box1: list[list[int]], box2: list[list[int]]) -> float:
        x1_min = min(point[0] for point in box1)
        y1_min = min(point[1] for point in box1)
        x1_max = max(point[0] for point in box1)
        y1_max = max(point[1] for point in box1)
        x2_min = min(point[0] for point in box2)
        y2_min = min(point[1] for point in box2)
        x2_max = max(point[0] for point in box2)
        y2_max = max(point[1] for point in box2)

        inter_x = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
        inter_y = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
        inter_area = inter_x * inter_y

        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area
        return inter_area / union_area if union_area > 0 else 0.0
