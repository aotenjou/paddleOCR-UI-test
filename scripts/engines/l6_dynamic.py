from __future__ import annotations

from typing import List

from core.models import DetectionContext, Issue

from .base import BaseLevelDetector


class DynamicContentDetector(BaseLevelDetector):
    level = "L6"
    name = "dynamic_content"
    description = "Compare before and after OCR snapshots for state changes."
    required_capabilities = ("has_actions",)

    def run(self, context: DetectionContext) -> List[Issue]:
        if not context.before_ocr or not context.after_ocr:
            return []

        rules = context.rules.get("dynamic-content", {})
        before_texts = [item.get("text", "") for item in context.before_ocr.get("texts", []) if item.get("text")]
        after_texts = [item.get("text", "") for item in context.after_ocr.get("texts", []) if item.get("text")]
        before_set = set(before_texts)
        after_set = set(after_texts)
        max_changes = rules.get("max_tracked_changes", 5)
        issues: List[Issue] = []

        removed = sorted(before_set - after_set)
        added = sorted(after_set - before_set)
        for text in removed[:max_changes]:
            issues.append(
                self.issue(
                    issue_type="content_removed",
                    severity="info",
                    element="dynamic",
                    expected="Text persists",
                    actual=f"Text '{text[:50]}' no longer visible",
                    suggestion="Expected for loading states; verify if intended",
                )
            )
        for text in added[:max_changes]:
            issues.append(
                self.issue(
                    issue_type="content_added",
                    severity="info",
                    element="dynamic",
                    expected="No new content",
                    actual=f"New text: '{text[:50]}'",
                    suggestion="Verify new content is expected after interaction",
                )
            )

        for name, transition in rules.get("state_transitions", {}).items():
            should_disappear = transition.get("should_disappear", [])
            should_appear = transition.get("should_appear", [])
            triggered = any(self._contains_token(before_texts, token) for token in should_disappear)
            if not triggered:
                continue

            still_visible = [token for token in should_disappear if self._contains_token(after_texts, token)]
            if still_visible:
                issues.append(
                    self.issue(
                        issue_type="state_transition_stuck",
                        severity="warning",
                        element=name,
                        expected=f"Tokens disappear: {', '.join(should_disappear)}",
                        actual=f"Still visible after action: {', '.join(still_visible)}",
                        suggestion="Check async state handling or waiting conditions",
                    )
                )

            if should_appear:
                appeared = [token for token in should_appear if self._contains_token(after_texts, token)]
                if not appeared:
                    issues.append(
                        self.issue(
                            issue_type="state_transition_missing_followup",
                            severity="warning",
                            element=name,
                            expected=f"At least one follow-up token appears: {', '.join(should_appear)}",
                            actual="No expected follow-up content detected",
                            suggestion="Verify post-action rendering completed successfully",
                        )
                    )

        persistence = rules.get("content_persistence", {})
        if persistence.get("enabled", False):
            for critical_text in persistence.get("critical_texts", []):
                if self._contains_token(before_texts, critical_text) and not self._contains_token(after_texts, critical_text):
                    issues.append(
                        self.issue(
                            issue_type="critical_content_removed",
                            severity="warning",
                            element="dynamic",
                            expected=f"Critical text persists: {critical_text}",
                            actual="Critical text disappeared after interaction",
                            suggestion="Check whether the state transition dropped required content",
                        )
                    )

        return issues

    @staticmethod
    def _contains_token(texts: List[str], token: str) -> bool:
        token_lower = token.lower()
        return any(token_lower in text.lower() for text in texts)

    def missing_capabilities(self, context: DetectionContext) -> List[str]:
        missing = super().missing_capabilities(context)
        if not context.before_ocr or not context.after_ocr:
            missing.append("has_action_ocr_pair")
        return missing
