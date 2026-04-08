#!/usr/bin/env python3
"""Compare OCR results against DOM/Accessibility Tree."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from core.a11y import flatten_a11y_tree
from core.config import load_rules
from core.text_utils import build_cross_validation_findings


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare(
    ocr_texts: List[Dict[str, Any]],
    a11y_elements: List[Dict[str, Any]],
    rules: Dict[str, Any],
) -> Dict[str, Any]:
    return build_cross_validation_findings(ocr_texts, a11y_elements, rules)


def main() -> None:
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

    rules = load_rules(args.rules)
    ocr_data = load_json(args.ocr)
    a11y_data = load_json(args.a11y)

    ocr_texts = ocr_data.get("texts", []) if isinstance(ocr_data, dict) else ocr_data
    if isinstance(a11y_data, dict):
        a11y_elements = flatten_a11y_tree(a11y_data, leaf_only=True)
    else:
        a11y_elements = a11y_data

    report = compare(ocr_texts, a11y_elements, rules=rules)
    Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Cross-validation report: {args.output}")
    print(f"  A11y texts: {report['summary']['a11y_text_count']}")
    print(f"  OCR texts:  {report['summary']['ocr_text_count']}")
    print(f"  Matching:   {report['summary']['matching']}")
    print(f"  Issues:     {report['summary']['issues']}")

    if args.ci:
        severities = [issue.get("severity", "info") for issue in report.get("issues", [])]
        if args.fail_on == "error" and "error" in severities:
            sys.exit(1)
        if args.fail_on == "warning" and any(
            severity in {"error", "warning"} for severity in severities
        ):
            sys.exit(1)


if __name__ == "__main__":
    main()
