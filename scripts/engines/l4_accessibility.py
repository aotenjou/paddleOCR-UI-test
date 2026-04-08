from __future__ import annotations

import re
from typing import List

from core.models import DetectionContext, Issue

from .base import BaseLevelDetector


class AccessibilityDetector(BaseLevelDetector):
    level = "L4"
    name = "accessibility"
    description = "Check accessible naming and text exposure issues."
    required_capabilities = ("has_a11y",)

    def run(self, context: DetectionContext) -> List[Issue]:
        rules = context.rules.get("accessibility", {})
        issues: List[Issue] = []

        missing_alt = rules.get("missing_alt", {})
        if missing_alt.get("enabled", True):
            roles = set(missing_alt.get("roles", ["image", "graphic", "img"]))
            ignore_values = set(missing_alt.get("ignore_values", ["", "image", "icon"]))
            for element in context.a11y_elements:
                if element.get("role") in roles and (element.get("text") or "") in ignore_values:
                    issues.append(
                        self.issue(
                            issue_type="missing_alt",
                            severity=missing_alt.get("severity", "error"),
                            element=f"{element.get('role')} at {element.get('path', 'unknown')}",
                            expected="Descriptive alt text",
                            actual=element.get("text", "(empty)"),
                            suggestion="Add meaningful alt text to the image",
                        )
                    )

        missing_label = rules.get("missing_label", {})
        if missing_label.get("enabled", False):
            interactive_roles = set(missing_label.get("roles", ["button", "textbox", "checkbox", "radio", "combobox"]))
            for element in context.a11y_elements:
                if element.get("role") in interactive_roles and not element.get("text"):
                    issues.append(
                        self.issue(
                            issue_type="missing_label",
                            severity=missing_label.get("severity", "error"),
                            element=f"{element.get('role')} at {element.get('path', 'unknown')}",
                            expected="Accessible label or aria-label",
                            actual="No accessible name",
                            suggestion="Add aria-label or visible label for screen readers",
                        )
                    )

        if rules.get("canvas_rendered_text", {}).get("enabled", False):
            a11y_texts = {element.get("text") for element in context.a11y_elements if element.get("text")}
            for item in context.ocr_result.get("texts", []):
                text = item.get("text", "").strip()
                if text and text not in a11y_texts and item.get("box"):
                    issues.append(
                        self.issue(
                            issue_type="canvas_rendered_text",
                            severity=rules.get("canvas_rendered_text", {}).get("severity", "warning"),
                            element=f"text at {item.get('box')}",
                            expected="Text should be represented in the accessibility tree",
                            actual=f"Text '{text[:50]}' only visible via OCR",
                            screenshot_region=item.get("box"),
                            suggestion="Text may be canvas-rendered or missing semantics",
                        )
                    )

        emoji_rules = rules.get("emoji_as_icon", {})
        if emoji_rules.get("enabled", False):
            emoji_pattern = re.compile(emoji_rules.get("emoji_pattern", r"[☀-➿]"))
            for element in context.a11y_elements:
                text = (element.get("text") or "").strip()
                if text and emoji_pattern.fullmatch(text):
                    issues.append(
                        self.issue(
                            issue_type="emoji_as_icon",
                            severity=emoji_rules.get("severity", "warning"),
                            element=f"{element.get('role', 'unknown')} at {element.get('path', 'unknown')}",
                            expected="Semantic icon or accessible label",
                            actual=f"Emoji-only accessible name: {text}",
                            suggestion="Use a semantic icon with an explicit accessible label",
                        )
                    )

        return issues
