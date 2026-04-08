from __future__ import annotations

import re
from typing import List

from core.models import DetectionContext, Issue
from core.text_utils import build_cross_validation_findings

from .base import BaseLevelDetector


class DomConsistencyDetector(BaseLevelDetector):
    level = "L3"
    name = "dom_consistency"
    description = "Cross-validate OCR text against accessibility tree content."
    required_capabilities = ("has_a11y",)

    def run(self, context: DetectionContext) -> List[Issue]:
        issues: List[Issue] = []
        findings = build_cross_validation_findings(
            context.ocr_result.get("texts", []),
            context.a11y_elements,
            context.rules,
        )
        for finding in findings.get("issues", []):
            issue_type = finding.get("type", "unknown")
            if issue_type == "text_mismatch":
                issues.append(
                    self.issue(
                        issue_type=issue_type,
                        severity=finding.get("severity", "warning"),
                        element="unknown",
                        expected=f"Text '{finding.get('a11y_text', '')}'",
                        actual=(
                            f"Closest OCR match: '{finding.get('closest_ocr', '')}' "
                            f"(similarity: {finding.get('similarity', 0):.2f})"
                        ),
                        suggestion="Possible typo or rendering issue",
                        evidence=finding,
                    )
                )
            elif issue_type == "dom_not_rendered":
                issues.append(
                    self.issue(
                        issue_type=issue_type,
                        severity=finding.get("severity", "error"),
                        element="unknown",
                        expected=f"Text '{finding.get('a11y_text', '')}' should be visible",
                        actual="Not detected in screenshot by OCR",
                        suggestion="Element may be hidden, off-screen, or visually clipped",
                        evidence=finding,
                    )
                )
            elif issue_type == "rendered_not_in_dom":
                issues.append(
                    self.issue(
                        issue_type=issue_type,
                        severity=finding.get("severity", "warning"),
                        element="unknown",
                        expected="All visible text should be represented in the accessibility tree",
                        actual=f"Text '{finding.get('ocr_text', '')}' visible but not exposed in DOM/A11y",
                        suggestion="May be canvas-rendered text or missing semantics",
                        evidence=finding,
                    )
                )
            elif issue_type == "count_mismatch":
                issues.append(
                    self.issue(
                        issue_type=issue_type,
                        severity=finding.get("severity", "warning"),
                        element="page",
                        expected=f"~{finding.get('a11y_count', 0)} text elements in DOM",
                        actual=f"{finding.get('ocr_count', 0)} text regions in screenshot",
                        suggestion="Large discrepancy may indicate rendering issues or hidden content",
                        evidence=finding,
                    )
                )

        issues.extend(self._check_expected_elements(context))
        return issues

    def _check_expected_elements(self, context: DetectionContext) -> List[Issue]:
        expected_elements = context.config.get("expected_elements", [])
        issues: List[Issue] = []
        for spec in expected_elements:
            pattern = spec.get("name_pattern")
            regex = re.compile(pattern) if pattern else None
            matches = []
            for element in context.a11y_elements:
                if element.get("role") != spec.get("role"):
                    continue
                text = element.get("text", "")
                if regex and not regex.search(text):
                    continue
                matches.append(element)

            min_count = spec.get("min_count", 1)
            max_count = spec.get("max_count")
            descriptor = spec.get("role", "element")
            if pattern:
                descriptor = f"{descriptor} /{pattern}/"

            if len(matches) < min_count:
                issues.append(
                    self.issue(
                        issue_type="expected_element_missing",
                        severity="error",
                        element=descriptor,
                        expected=f"At least {min_count} matching elements",
                        actual=f"Found {len(matches)}",
                        suggestion="Check role/name mapping in the page structure",
                        evidence={"spec": spec, "matches": len(matches)},
                    )
                )
            if max_count is not None and len(matches) > max_count:
                issues.append(
                    self.issue(
                        issue_type="expected_element_count_mismatch",
                        severity="warning",
                        element=descriptor,
                        expected=f"At most {max_count} matching elements",
                        actual=f"Found {len(matches)}",
                        suggestion="Verify duplicated or unexpected elements in the rendered structure",
                        evidence={"spec": spec, "matches": len(matches)},
                    )
                )
        return issues
