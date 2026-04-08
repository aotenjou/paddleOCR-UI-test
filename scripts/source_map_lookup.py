#!/usr/bin/env python3
"""
Source Map Lookup - Map UI test issues to source code locations.

Uses DOM element coordinates and source maps to resolve visual issues
back to the original source file and line number.

Usage:
    python3 source_map_lookup.py --screenshot screenshot.png --dom dom_elements.json \
        --source-map ./dist --issue issue.json --output resolved.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_json(path: str) -> Any:
    """Load JSON from file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_element_at_position(
    dom_elements: List[Dict[str, Any]], x: int, y: int
) -> Optional[Dict[str, Any]]:
    """Find the DOM element that contains the given pixel position."""
    candidates = []
    for elem in dom_elements:
        bounds = elem.get("bounds", {})
        bx = bounds.get("x", 0)
        by = bounds.get("y", 0)
        bw = bounds.get("width", 0)
        bh = bounds.get("height", 0)
        if bx <= x <= bx + bw and by <= y <= by + bh:
            candidates.append((bw * bh, elem))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def lookup_source_location(
    source_map_dir: str, file_path: str, line: int
) -> Dict[str, Any]:
    """
    Resolve a compiled file path and line to original source location.

    In production this would use the `sourcemap` library to parse .map files.
    For now, this is a placeholder that returns the input if no source map
    files are found.
    """
    sm_dir = Path(source_map_dir)
    if not sm_dir.exists():
        return {
            "file": file_path,
            "line": line,
            "resolved": False,
            "reason": "source-map dir not found",
        }

    map_files = list(sm_dir.rglob("*.map"))
    if not map_files:
        return {
            "file": file_path,
            "line": line,
            "resolved": False,
            "reason": "no .map files found",
        }

    for mf in map_files:
        try:
            sm = json.loads(mf.read_text())
            sources = sm.get("sources", [])
            for src in sources:
                if file_path.endswith(src) or src.endswith(file_path.split("/")[-1]):
                    return {
                        "file": src,
                        "line": line,
                        "resolved": True,
                        "source_map": str(mf),
                    }
        except (json.JSONDecodeError, KeyError):
            continue

    return {
        "file": file_path,
        "line": line,
        "resolved": False,
        "reason": "no matching source map entry",
    }


def resolve_issues(
    issues: List[Dict[str, Any]],
    dom_elements: List[Dict[str, Any]],
    source_map_dir: str,
) -> List[Dict[str, Any]]:
    """Add source_location to each issue."""
    for issue in issues:
        region = issue.get("screenshot_region")
        if not region or len(region) < 2:
            issue["source_location"] = {"resolved": False, "reason": "no region data"}
            continue

        x = region[0][0]
        y = region[0][1]
        elem = find_element_at_position(dom_elements, x, y)

        if not elem:
            issue["source_location"] = {
                "resolved": False,
                "reason": f"no DOM element at ({x}, {y})",
                "pixel": [x, y],
            }
            continue

        tag = elem.get("tagName", "").lower()
        data_file = elem.get("data-file", "")
        data_line = elem.get("data-line", 0)

        if data_file:
            loc = lookup_source_location(source_map_dir, data_file, int(data_line))
            issue["source_location"] = loc
        else:
            issue["source_location"] = {
                "resolved": False,
                "reason": f"element <{tag}> has no data-file attribute",
                "element": {"tag": tag, "name": elem.get("name", "")},
                "hint": "Enable data-component attributes in dev mode for precise mapping",
            }

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Map UI issues to source code locations"
    )
    parser.add_argument(
        "--issues", required=True, help="Issues JSON file (from ui_test.py)"
    )
    parser.add_argument("--dom", required=True, help="DOM elements JSON file")
    parser.add_argument("--source-map", required=True, help="Source map directory")
    parser.add_argument("--output", default="resolved_issues.json", help="Output file")
    args = parser.parse_args()

    issues_data = load_json(args.issues)
    issues = (
        issues_data.get("results", issues_data)
        if isinstance(issues_data, dict)
        else issues_data
    )
    dom_elements = load_json(args.dom)

    if isinstance(dom_elements, dict):
        from core.a11y import flatten_a11y_tree

        dom_elements = flatten_a11y_tree(dom_elements, leaf_only=False)

    resolved = resolve_issues(issues, dom_elements, args.source_map)

    Path(args.output).write_text(json.dumps(resolved, indent=2, ensure_ascii=False))

    resolved_count = sum(
        1 for r in resolved if r.get("source_location", {}).get("resolved")
    )
    print(f"Resolved issues: {args.output}")
    print(f"  Total: {len(resolved)}")
    print(f"  Resolved to source: {resolved_count}")
    print(f"  Unresolved: {len(resolved) - resolved_count}")


if __name__ == "__main__":
    main()
