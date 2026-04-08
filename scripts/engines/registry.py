from __future__ import annotations

from typing import Dict, List

from core.models import (
    DetectionContext,
    DetectionOutcome,
    coerce_execution_records,
    coerce_issues,
)

from .l1_text import TextConsistencyDetector
from .l2_layout import LayoutReasonablenessDetector
from .l3_dom import DomConsistencyDetector
from .l4_accessibility import AccessibilityDetector
from .l5_i18n import InternationalizationDetector
from .l6_dynamic import DynamicContentDetector


DETECTOR_REGISTRY = {
    "L1": TextConsistencyDetector(),
    "L2": LayoutReasonablenessDetector(),
    "L3": DomConsistencyDetector(),
    "L4": AccessibilityDetector(),
    "L5": InternationalizationDetector(),
    "L6": DynamicContentDetector(),
}


def list_detectors(detailed: bool = False) -> List:
    if detailed:
        return [
            DETECTOR_REGISTRY[level].descriptor()
            for level in sorted(DETECTOR_REGISTRY)
        ]
    return sorted(DETECTOR_REGISTRY)


def execute_levels(levels: List[str], context: DetectionContext) -> DetectionOutcome:
    issues = []
    execution = []
    for level in levels:
        detector = DETECTOR_REGISTRY.get(level)
        if detector is None:
            execution.append(
                {
                    "level": level,
                    "detector": "unknown",
                    "status": "skipped",
                    "reason": "unregistered detector",
                }
            )
            continue
        missing_capabilities = detector.missing_capabilities(context)
        if missing_capabilities:
            execution.append(
                detector.execution_record(
                    status="skipped",
                    reason="missing required capabilities",
                    missing_capabilities=missing_capabilities,
                )
            )
            continue
        issues.extend(detector.run(context))
        execution.append(detector.execution_record(status="executed"))
    return DetectionOutcome(
        issues=coerce_issues(issues),
        execution=coerce_execution_records(execution),
    )


def run_levels(levels: List[str], context: DetectionContext) -> List[dict]:
    return execute_levels(levels, context).issues
