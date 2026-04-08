from __future__ import annotations

import json
from pathlib import Path

from .base import EvidenceBundle, InputAdapter


class MCPPayloadAdapter(InputAdapter):
    name = "mcp"

    async def load_bundle(self) -> EvidenceBundle:
        input_json_path = Path(self.args.input_json).resolve()
        if not input_json_path.exists():
            raise ValueError(f"Input JSON not found: {input_json_path}")

        payload = json.loads(input_json_path.read_text(encoding="utf-8"))
        base_dir = input_json_path.parent

        screenshot_file = payload.get("screenshot_path")
        if not screenshot_file:
            raise ValueError("MCP payload missing required field: screenshot_path")
        screenshot_path = self._resolve_path(screenshot_file, base_dir=base_dir)
        if not screenshot_path.exists():
            raise ValueError(f"MCP screenshot file not found: {screenshot_path}")

        a11y_tree = {}
        if "a11y_tree" in payload and isinstance(payload["a11y_tree"], dict):
            a11y_tree = payload["a11y_tree"]
        elif payload.get("a11y_tree_path"):
            a11y_tree_path = self._resolve_path(
                payload["a11y_tree_path"], base_dir=base_dir
            )
            if a11y_tree_path.exists():
                a11y_tree = json.loads(a11y_tree_path.read_text(encoding="utf-8"))

        dom_html = ""
        if payload.get("dom_html"):
            dom_html = payload["dom_html"]
        elif payload.get("dom_path"):
            dom_path = self._resolve_path(payload["dom_path"], base_dir=base_dir)
            if dom_path.exists():
                dom_html = dom_path.read_text(encoding="utf-8")

        return EvidenceBundle(
            screenshot_path=str(screenshot_path),
            a11y_tree=a11y_tree,
            dom_html=dom_html,
            url=payload.get("url", self.args.url or ""),
            viewport=payload.get("viewport", self.args.viewport or ""),
            source=self.args.source or payload.get("source", "mcp"),
            extras={"input_json": str(input_json_path)},
        )
