from __future__ import annotations

from typing import List, Optional

from core.models import DetectionContext, ExecutionRecord, Issue


class BaseLevelDetector:
    level = ""
    name = ""
    description = ""
    required_capabilities: tuple[str, ...] = ()
    optional_capabilities: tuple[str, ...] = ()

    def issue(
        self,
        *,
        issue_type: str,
        severity: str,
        element: str,
        expected: str,
        actual: str,
        screenshot_region: Optional[list[list[int]]] = None,
        suggestion: str = "",
        evidence: Optional[dict] = None,
        meta: Optional[dict] = None,
    ) -> Issue:
        return Issue(
            type=issue_type,
            level=self.level,
            severity=severity,
            element=element,
            expected=expected,
            actual=actual,
            screenshot_region=screenshot_region,
            suggestion=suggestion,
            evidence=evidence or {},
            meta=meta or {},
        )

    def run(self, context: DetectionContext) -> List[Issue]:
        raise NotImplementedError

    def missing_capabilities(self, context: DetectionContext) -> List[str]:
        capabilities = context.capabilities()
        return [
            capability
            for capability in self.required_capabilities
            if not capabilities.get(capability, False)
        ]

    def descriptor(self) -> dict:
        return {
            "level": self.level,
            "name": self.name or self.__class__.__name__,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "optional_capabilities": list(self.optional_capabilities),
        }

    def execution_record(
        self,
        *,
        status: str,
        reason: str = "",
        missing_capabilities: Optional[List[str]] = None,
    ) -> ExecutionRecord:
        return ExecutionRecord(
            level=self.level,
            detector=self.name or self.__class__.__name__,
            status=status,
            reason=reason,
            required_capabilities=list(self.required_capabilities),
            missing_capabilities=missing_capabilities or [],
        )
