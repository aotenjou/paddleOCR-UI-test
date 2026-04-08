from __future__ import annotations

from .artifact_dir import ArtifactDirAdapter
from .mcp_payload import MCPPayloadAdapter


def detect_input_mode(args) -> str:
    if args.input_mode and args.input_mode != "auto":
        return args.input_mode
    if args.input_json:
        return "mcp"
    if args.artifacts_dir:
        return "artifacts"
    return "url"


def build_adapter(args):
    mode = detect_input_mode(args)
    if mode == "mcp":
        if not args.input_json:
            raise ValueError("--input-mode mcp requires --input-json")
        return MCPPayloadAdapter(args), mode
    if mode == "artifacts":
        if not args.artifacts_dir:
            raise ValueError("--input-mode artifacts requires --artifacts-dir")
        return ArtifactDirAdapter(args), mode
    return None, "url"
