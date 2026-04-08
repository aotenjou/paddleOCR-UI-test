from __future__ import annotations

from typing import Any, Dict, List


def flatten_a11y_tree(
    tree: Dict[str, Any],
    *,
    leaf_only: bool = True,
    include_empty: bool = False,
) -> List[Dict[str, Any]]:
    """Flatten an accessibility tree to a list of nodes.

    By default only leaf nodes are returned to avoid duplicate text inherited
    from ancestor textContent values.
    """

    elements: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], path: str = "") -> None:
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        bounds = node.get("bounds", {})
        text = (name or value or "").strip()
        children = node.get("children", []) or []

        is_leaf = len(children) == 0
        if (include_empty or text) and (not leaf_only or is_leaf):
            elements.append(
                {
                    "role": role,
                    "text": text,
                    "bounds": bounds,
                    "path": path,
                    "tagName": node.get("tagName", ""),
                }
            )

        for index, child in enumerate(children):
            child_path = f"{path}/{role}[{index}]" if path else f"{role}[{index}]"
            walk(child, child_path)

    if tree:
        walk(tree)
    return elements
