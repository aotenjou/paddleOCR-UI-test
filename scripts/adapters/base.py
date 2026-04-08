from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.models import EvidenceBundle


class InputAdapter:
    name = "base"
    description = ""
    produced_capabilities: tuple[str, ...] = ()

    def __init__(self, args: Any):
        self.args = args

    async def load_bundle(self) -> EvidenceBundle:
        raise NotImplementedError

    @classmethod
    def descriptor(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "description": cls.description,
            "produced_capabilities": list(cls.produced_capabilities),
        }

    @staticmethod
    def _resolve_path(path_value: str, base_dir: Optional[Path] = None) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        if base_dir:
            return (base_dir / path).resolve()
        return path.resolve()
