#!/usr/bin/env python3
"""Lightweight smoke checks for input modes (url/artifacts/mcp).

This validates adapter routing and payload loading without hitting network
or OCR APIs. Temporary files are created under a temp directory and removed
automatically after completion.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import tempfile
from pathlib import Path

from adapters.registry import build_adapter, detect_input_mode


MIN_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAgMBgJvX9dUAAAAASUVORK5CYII="
)


def _write_min_files(root: Path) -> None:
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    (artifacts / "screenshot.png").write_bytes(base64.b64decode(MIN_PNG_B64))
    (artifacts / "a11y_tree.json").write_text(
        json.dumps({"role": "document", "name": "Root", "children": []}),
        encoding="utf-8",
    )
    (artifacts / "dom.html").write_text(
        "<html><body>ok</body></html>", encoding="utf-8"
    )
    (artifacts / "metadata.json").write_text(
        json.dumps(
            {
                "url": "https://example.com",
                "viewport": "1280x720",
                "source": "playwright-mcp",
            }
        ),
        encoding="utf-8",
    )

    (root / "mcp-payload.json").write_text(
        json.dumps(
            {
                "source": "ui-test-generation-mcp",
                "url": "https://example.com",
                "viewport": "1280x720",
                "screenshot_path": "./artifacts/screenshot.png",
                "a11y_tree_path": "./artifacts/a11y_tree.json",
                "dom_path": "./artifacts/dom.html",
            }
        ),
        encoding="utf-8",
    )


def _args(**kwargs):
    defaults = dict(
        input_mode="auto",
        input_json=None,
        artifacts_dir=None,
        url=None,
        viewport=None,
        source=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


async def _run() -> None:
    with tempfile.TemporaryDirectory(prefix="paddle-smoke-") as td:
        root = Path(td)
        _write_min_files(root)

        # URL mode route check
        url_args = _args(url="https://example.com")
        assert detect_input_mode(url_args) == "url"
        adapter, mode = build_adapter(url_args)
        assert adapter is None and mode == "url"

        # Artifacts mode route + load check
        artifacts_args = _args(
            input_mode="artifacts",
            artifacts_dir=str(root / "artifacts"),
            source="playwright-mcp",
        )
        assert detect_input_mode(artifacts_args) == "artifacts"
        adapter, mode = build_adapter(artifacts_args)
        assert adapter is not None and mode == "artifacts"
        bundle = await adapter.load_bundle()
        assert bundle.screenshot_path.endswith("screenshot.png")
        assert bundle.a11y_tree.get("role") == "document"

        # MCP mode route + load check
        mcp_args = _args(
            input_mode="mcp",
            input_json=str(root / "mcp-payload.json"),
        )
        assert detect_input_mode(mcp_args) == "mcp"
        adapter, mode = build_adapter(mcp_args)
        assert adapter is not None and mode == "mcp"
        bundle = await adapter.load_bundle()
        assert bundle.screenshot_path.endswith("screenshot.png")
        assert bundle.source == "ui-test-generation-mcp"

        print("Smoke checks passed: url/artifacts/mcp input modes")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
