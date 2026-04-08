from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


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


class InputAdapter:
    name = "base"

    def __init__(self, args: Any):
        self.args = args

    async def load_bundle(self) -> EvidenceBundle:
        raise NotImplementedError

    @staticmethod
    def _resolve_path(path_value: str, base_dir: Optional[Path] = None) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        if base_dir:
            return (base_dir / path).resolve()
        return path.resolve()
