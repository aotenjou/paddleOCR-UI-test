from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


@dataclass
class EvidenceBundle:
    screenshot_path: str
    a11y_tree: Dict[str, Any] = field(default_factory=dict)
    dom_html: Optional[str] = None
    url: str = ""
    viewport: str = ""
    source: str = "standalone"
    state: str = "current"
    extras: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.1"
    capabilities: Dict[str, bool] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        defaults = {
            "has_dom": bool(self.dom_html),
            "has_a11y": bool(self.a11y_tree),
            "has_actions": False,
            "has_source_map": bool(self.extras.get("source_map")),
        }
        defaults.update(self.capabilities)
        self.capabilities = defaults

        provenance = {
            "source": self.source,
            "state": self.state,
        }
        provenance.update(self.provenance)
        self.provenance = provenance

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    type: str
    level: str
    severity: str
    element: str
    expected: str
    actual: str
    screenshot_region: Optional[List[List[int]]] = None
    suggestion: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    source_location: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not self.screenshot_region:
            data.pop("screenshot_region", None)
        if not self.source_location:
            data.pop("source_location", None)
        if not self.evidence:
            data.pop("evidence", None)
        if not self.meta:
            data.pop("meta", None)
        if not self.suggestion:
            data.pop("suggestion", None)
        return data


@dataclass
class DetectionContext:
    ocr_result: Dict[str, Any]
    a11y_elements: List[Dict[str, Any]]
    config: Dict[str, Any]
    image_size: Tuple[int, int]
    rules: Dict[str, Any] = field(default_factory=dict)
    evidence: Optional[EvidenceBundle] = None
    before_ocr: Optional[Dict[str, Any]] = None
    after_ocr: Optional[Dict[str, Any]] = None

    def capabilities(self) -> Dict[str, bool]:
        base = dict(self.evidence.capabilities) if self.evidence else {}
        inferred = {
            "has_dom": bool(self.evidence and self.evidence.dom_html),
            "has_a11y": bool(self.a11y_elements),
            "has_actions": bool(base.get("has_actions"))
            and bool(self.before_ocr)
            and bool(self.after_ocr),
            "has_source_map": bool(base.get("has_source_map")),
        }
        inferred.update(base)
        if self.before_ocr and self.after_ocr:
            inferred["has_actions"] = True
        return inferred


@dataclass
class ExecutionRecord:
    level: str
    detector: str
    status: str
    reason: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    missing_capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not self.reason:
            data.pop("reason", None)
        if not self.required_capabilities:
            data.pop("required_capabilities", None)
        if not self.missing_capabilities:
            data.pop("missing_capabilities", None)
        return data


@dataclass
class DetectionOutcome:
    issues: List[Dict[str, Any]] = field(default_factory=list)
    execution: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": list(self.issues),
            "execution": coerce_execution_records(self.execution),
        }


IssueLike = Union[Issue, Dict[str, Any]]


def coerce_issue(issue: IssueLike) -> Dict[str, Any]:
    if isinstance(issue, Issue):
        return issue.to_dict()
    if is_dataclass(issue):
        return asdict(issue)
    return dict(issue)


def coerce_issues(issues: Iterable[IssueLike]) -> List[Dict[str, Any]]:
    return [coerce_issue(issue) for issue in issues]


ExecutionRecordLike = Union[ExecutionRecord, Dict[str, Any]]


def coerce_execution_record(record: ExecutionRecordLike) -> Dict[str, Any]:
    if isinstance(record, ExecutionRecord):
        return record.to_dict()
    if is_dataclass(record):
        return asdict(record)
    return dict(record)


def coerce_execution_records(
    records: Iterable[ExecutionRecordLike],
) -> List[Dict[str, Any]]:
    return [coerce_execution_record(record) for record in records]
