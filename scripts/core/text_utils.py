from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Pattern, Sequence, Tuple


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def compile_patterns(patterns: Iterable[str]) -> List[Pattern[str]]:
    return [re.compile(pattern) for pattern in patterns or []]


def matches_any_pattern(text: str, patterns: Sequence[Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def text_similarity(a: str, b: str) -> float:
    a_norm = normalize_text(a).lower()
    b_norm = normalize_text(b).lower()
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    if a_norm in b_norm or b_norm in a_norm:
        return 0.8

    m, n = len(a_norm), len(b_norm)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a_norm[i - 1] == b_norm[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n] / max(m, n)


def find_best_match(
    query: str, candidates: Sequence[str], threshold: float = 0.6
) -> Tuple[Optional[str], float]:
    best_match: Optional[str] = None
    best_score = 0.0
    for candidate in candidates:
        score = text_similarity(query, candidate)
        if score > best_score:
            best_match = candidate
            best_score = score
    if best_score >= threshold:
        return best_match, best_score
    return None, best_score


def distinct_texts(items: Iterable[Dict[str, Any]], key: str = "text") -> List[str]:
    seen = set()
    results = []
    for item in items:
        text = normalize_text(str(item.get(key, "")))
        if text and text not in seen:
            seen.add(text)
            results.append(text)
    return results


def build_cross_validation_findings(
    ocr_texts: Sequence[Dict[str, Any]],
    a11y_elements: Sequence[Dict[str, Any]],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    dom_rules = (rules or {}).get("dom-ocr-crossval", {})
    fuzzy_cfg = dom_rules.get("fuzzy_match", {})
    count_cfg = dom_rules.get("count_mismatch", {})

    fuzzy_enabled = fuzzy_cfg.get("enabled", True)
    fuzzy_threshold = fuzzy_cfg.get("threshold", 0.6)
    warning_threshold = fuzzy_cfg.get("warning_threshold", 0.7)
    ignore_patterns = compile_patterns(dom_rules.get("ignore_patterns", []))

    ocr_text_list = distinct_texts(ocr_texts)
    a11y_text_list = distinct_texts(a11y_elements)
    ocr_set = set(ocr_text_list)
    a11y_set = set(a11y_text_list)

    issues: List[Dict[str, Any]] = []
    matched_a11y = set()

    for a11y_text in a11y_text_list:
        if matches_any_pattern(a11y_text, ignore_patterns):
            matched_a11y.add(a11y_text)
            continue

        if a11y_text in ocr_set:
            matched_a11y.add(a11y_text)
            continue

        if fuzzy_enabled:
            best_match, similarity = find_best_match(
                a11y_text, ocr_text_list, threshold=fuzzy_threshold
            )
            if best_match is not None:
                matched_a11y.add(a11y_text)
                issues.append(
                    {
                        "type": "text_mismatch",
                        "severity": "warning"
                        if similarity >= warning_threshold
                        else "error",
                        "a11y_text": a11y_text,
                        "closest_ocr": best_match,
                        "similarity": round(similarity, 3),
                        "description": (
                            f"DOM says '{a11y_text}', OCR sees '{best_match}' "
                            f"(similarity: {similarity:.1%})"
                        ),
                    }
                )
                continue

        issues.append(
            {
                "type": "dom_not_rendered",
                "severity": dom_rules.get("dom_not_rendered", {}).get(
                    "severity", "error"
                ),
                "a11y_text": a11y_text,
                "description": (
                    f"Text '{a11y_text}' exists in DOM but not visible in screenshot"
                ),
            }
        )

    rendered_not_in_dom_max = dom_rules.get("rendered_not_in_dom", {}).get(
        "max_results", 10
    )
    for text in ocr_text_list:
        if text in a11y_set or matches_any_pattern(text, ignore_patterns):
            continue
        issues.append(
            {
                "type": "rendered_not_in_dom",
                "severity": dom_rules.get("rendered_not_in_dom", {}).get(
                    "severity", "warning"
                ),
                "ocr_text": text,
                "description": (
                    f"Text '{text}' visible in screenshot but not in accessibility tree"
                ),
            }
        )
        if sum(1 for issue in issues if issue["type"] == "rendered_not_in_dom") >= rendered_not_in_dom_max:
            break

    delta_threshold = count_cfg.get("delta_threshold", 0.3)
    min_elements = count_cfg.get("min_elements", 5)
    count_delta = abs(len(a11y_set) - len(ocr_set))
    max_count = max(len(a11y_set), len(ocr_set), 1)
    if (
        count_cfg.get("enabled", True)
        and count_delta > max_count * delta_threshold
        and len(a11y_set) > min_elements
    ):
        issues.append(
            {
                "type": "count_mismatch",
                "severity": count_cfg.get("severity", "warning"),
                "a11y_count": len(a11y_set),
                "ocr_count": len(ocr_set),
                "description": (
                    f"Text count mismatch: {len(a11y_set)} in DOM vs {len(ocr_set)} in OCR "
                    f"({count_delta / max_count:.0%} delta)"
                ),
            }
        )

    dom_not_rendered_max = dom_rules.get("dom_not_rendered", {}).get("max_results", 10)
    dom_not_rendered = [
        issue for issue in issues if issue["type"] == "dom_not_rendered"
    ][:dom_not_rendered_max]
    others = [issue for issue in issues if issue["type"] != "dom_not_rendered"]
    final_issues = dom_not_rendered + others

    return {
        "summary": {
            "a11y_text_count": len(a11y_set),
            "ocr_text_count": len(ocr_set),
            "matching": len(ocr_set & a11y_set),
            "issues": len(final_issues),
        },
        "issues": final_issues,
    }
