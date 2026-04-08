from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .base import EvidenceBundle, InputAdapter


class ArtifactDirAdapter(InputAdapter):
    name = "artifacts"
    description = "Load screenshot and optional DOM/A11y artifacts from a directory."
    produced_capabilities = ("has_dom", "has_a11y")

    async def load_bundle(self) -> EvidenceBundle:
        artifacts_dir = Path(self.args.artifacts_dir).resolve()
        if not artifacts_dir.exists() or not artifacts_dir.is_dir():
            raise ValueError(f"Invalid artifacts directory: {artifacts_dir}")

        screenshot_path = self._find_screenshot(artifacts_dir)
        a11y_tree = self._load_json_optional(
            artifacts_dir / "a11y_tree.json", default={}
        )
        dom_html = self._load_text_optional(artifacts_dir / "dom.html")
        meta = self._load_json_optional(artifacts_dir / "metadata.json", default={})

        return EvidenceBundle(
            screenshot_path=str(screenshot_path),
            a11y_tree=a11y_tree,
            dom_html=dom_html,
            url=meta.get("url", self.args.url or ""),
            viewport=meta.get("viewport", self.args.viewport or ""),
            source=self.args.source or meta.get("source", "artifacts"),
            extras={"artifacts_dir": str(artifacts_dir)},
            capabilities={
                "has_dom": bool(dom_html),
                "has_a11y": bool(a11y_tree),
                "has_actions": False,
            },
            provenance={
                "artifacts_dir": str(artifacts_dir),
                "metadata_file": str(artifacts_dir / "metadata.json"),
            },
        )

    def _find_screenshot(self, artifacts_dir: Path) -> Path:
        candidates = [
            artifacts_dir / "screenshot.png",
            artifacts_dir / "screenshot.jpg",
            artifacts_dir / "screenshot.jpeg",
            artifacts_dir / "screen.png",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise ValueError(
            f"No screenshot file found in {artifacts_dir}. "
            "Expected one of: screenshot.png/jpg/jpeg or screen.png"
        )

    @staticmethod
    def _load_json_optional(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_text_optional(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
