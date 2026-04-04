#!/usr/bin/env python3
"""
Compare OCR results against DOM/Accessibility Tree.

Standalone cross-validation engine that takes OCR output and A11y tree data,
produces a structured diff report.

Usage:
    python3 compare_ocr_dom.py --ocr ocr_result.json --a11y a11y_tree.json [--output report.json]
    python3 compare_ocr_dom.py --ocr ocr.json --a11y a11y.json --ci --fail-on error
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON from file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flatten_a11y_tree(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten accessibility tree to element list."""
    elements = []

    def walk(node: Dict[str, Any], path: str = ""):
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        bounds = node.get("bounds", {})
        text = (name or value or "").strip()

        if text:
            elements.append(
                {
                    "role": role,
                    "text": text,
                    "bounds": bounds,
                    "path": path,
                }
            )

        for i, child in enumerate(node.get("children", [])):
            child_path = f"{path}/{role}[{i}]" if path else f"{role}[{i}]"
            walk(child, child_path)

    if tree:
        walk(tree)
    return elements


def text_similarity(a: str, b: str) -> float:
    """Sequence-aware text similarity ratio (0.0 - 1.0).

    Uses longest common subsequence to detect typos that character-set
    based metrics miss (e.g. "Password" vs "Pasword" share the same
    character set but are different strings).
    """
    if not a or not b:
        return 0.0
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if a_lower == b_lower:
        return 1.0
    if a_lower in b_lower or b_lower in a_lower:
        return 0.8

    # Longest common subsequence length
    m, n = len(a_lower), len(b_lower)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a_lower[i - 1] == b_lower[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]

    # Normalise by the longer string length so short typos are penalised
    return lcs_len / max(m, n)


def find_best_match(
    query: str, candidates: List[str], threshold: float = 0.6
) -> Tuple[str, float]:
    """Find the best matching candidate text."""
    best = ("", 0.0)
    for cand in candidates:
        sim = text_similarity(query, cand)
        if sim > best[1]:
            best = (cand, sim)
    return best if best[1] >= threshold else ("", best[1])


def compare(
    ocr_texts: List[Dict],
    a11y_elements: List[Dict],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Cross-validate OCR results against A11y tree.

    Args:
        ocr_texts: List of OCR text dicts with 'text' key
        a11y_elements: List of A11y element dicts with 'text' key
        rules: Optional rule overrides for thresholds and ignore patterns
    """
    fuzzy_threshold = 0.6
    warn_threshold = 0.7
    ignore_patterns = []

    if rules:
        fuzzy_cfg = rules.get("dom-ocr-crossval", {}).get("fuzzy_match", {})
        if fuzzy_cfg.get("enabled", True):
            fuzzy_threshold = fuzzy_cfg.get("threshold", 0.6)
            warn_threshold = fuzzy_cfg.get("warning_threshold", 0.7)
        ignore_patterns = rules.get("dom-ocr-crossval", {}).get("ignore_patterns", [])

    import re

    ignore_res = [re.compile(p) for p in ignore_patterns]

    ocr_text_list = [t["text"].strip() for t in ocr_texts if t.get("text", "").strip()]
    a11y_text_list = [
        e["text"].strip() for e in a11y_elements if e.get("text", "").strip()
    ]

    ocr_set = set(ocr_text_list)
    a11y_set = set(a11y_text_list)

    issues = []

    for text in sorted(a11y_set - ocr_set):
        if any(p.search(text) for p in ignore_res):
            continue
        best_match, sim = find_best_match(
            text, ocr_text_list, threshold=fuzzy_threshold
        )
        if best_match and sim < 1.0:
            issues.append(
                {
                    "type": "text_mismatch",
                    "severity": "error" if sim < warn_threshold else "warning",
                    "a11y_text": text,
                    "closest_ocr": best_match,
                    "similarity": round(sim, 3),
                    "description": f"DOM says '{text}', OCR sees '{best_match}' (similarity: {sim:.1%})",
                }
            )
        else:
            issues.append(
                {
                    "type": "dom_not_rendered",
                    "severity": "error",
                    "a11y_text": text,
                    "description": f"Text '{text}' exists in DOM but not visible in screenshot",
                }
            )

    for text in sorted(ocr_set - a11y_set):
        if any(p.search(text) for p in ignore_res):
            continue
        issues.append(
            {
                "type": "rendered_not_in_dom",
                "severity": "warning",
                "ocr_text": text,
                "description": f"Text '{text}' visible in screenshot but not in accessibility tree",
            }
        )

    a11y_count = len(a11y_set)
    ocr_count = len(ocr_set)
    delta_threshold = 0.3
    min_elements = 5
    if rules:
        cm = rules.get("dom-ocr-crossval", {}).get("count_mismatch", {})
        delta_threshold = cm.get("delta_threshold", 0.3)
        min_elements = cm.get("min_elements", 5)

    count_delta = abs(a11y_count - ocr_count)
    if (
        count_delta > max(a11y_count, ocr_count) * delta_threshold
        and a11y_count > min_elements
    ):
        issues.append(
            {
                "type": "count_mismatch",
                "severity": "warning",
                "a11y_count": a11y_count,
                "ocr_count": ocr_count,
                "description": f"Text count mismatch: {a11y_count} in DOM vs {ocr_count} in OCR ({count_delta / max(a11y_count, ocr_count):.0%} delta)",
            }
        )

    return {
        "summary": {
            "a11y_text_count": len(a11y_set),
            "ocr_text_count": len(ocr_set),
            "matching": len(ocr_set & a11y_set),
            "issues": len(issues),
        },
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="OCR vs DOM cross-validation")
    parser.add_argument("--ocr", required=True, help="OCR result JSON file")
    parser.add_argument("--a11y", required=True, help="A11y tree JSON file")
    parser.add_argument(
        "--output", default="cross_validation_report.json", help="Output file"
    )
    parser.add_argument("--rules", help="Rules directory for config overrides")
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exit code 1 if issues found at or above --fail-on severity",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "warning"],
        default="error",
        help="Minimum severity to fail in CI mode (default: error)",
    )
    args = parser.parse_args()

    rules = None
    if args.rules:
        rules_path = Path(args.rules)
        rules = {}
        dom_rules_path = rules_path / "dom-ocr-crossval.json"
        if dom_rules_path.exists():
            rules["dom-ocr-crossval"] = json.loads(dom_rules_path.read_text())

    ocr_data = load_json(args.ocr)
    a11y_data = load_json(args.a11y)

    ocr_texts = ocr_data.get("texts", [])
    a11y_elements = flatten_a11y_tree(a11y_data)

    report = compare(ocr_texts, a11y_elements, rules=rules)

    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Cross-validation report: {args.output}")
    print(f"  A11y texts: {report['summary']['a11y_text_count']}")
    print(f"  OCR texts:  {report['summary']['ocr_text_count']}")
    print(f"  Matching:   {report['summary']['matching']}")
    print(f"  Issues:     {report['summary']['issues']}")

    if args.ci:
        has_failure = False
        for issue in report["issues"]:
            sev = issue.get("severity", "info")
            if args.fail_on == "error" and sev == "error":
                has_failure = True
                break
            elif args.fail_on == "warning" and sev in ("error", "warning"):
                has_failure = True
                break
        if has_failure:
            print(f"\nCI FAILED: issues found at or above '{args.fail_on}' severity")
            sys.exit(1)
        else:
            print(f"\nCI PASSED: no issues at or above '{args.fail_on}' severity")
            sys.exit(0)


if __name__ == "__main__":
    main()
