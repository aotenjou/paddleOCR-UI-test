#!/usr/bin/env python3
"""
PaddleOCR UI Test - Main execution script.

Combines PaddleOCR screenshot analysis with Playwright Accessibility Tree
for intelligent UI testing across 6 levels (L1-L6).

Supports data-driven rules, industry profiles, baseline regression testing,
and automated action sequences.

Usage:
    python3 ui_test.py --url https://example.com [options]
"""

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from playwright.async_api import async_playwright

try:
    from openai import AsyncOpenAI
except ImportError:
    print("Error: openai library required. Run: pip install openai")
    sys.exit(1)


# ─── Configuration ───────────────────────────────────────────────────────────

PADDLEOCR_API_KEY = os.environ.get("PADDLEOCR_API_KEY") or os.environ.get(
    "SILICONFLOW_API_KEY"
)
PADDLEOCR_MODEL = os.environ.get("PADDLEOCR_MODEL", "PaddlePaddle/PaddleOCR-VL-1.5")
PADDLEOCR_API_URL = os.environ.get("PADDLEOCR_API_URL", "https://api.siliconflow.cn/v1")

DEFAULT_RULES_DIR = Path(__file__).parent.parent / "rules"
DEFAULT_PROFILES_DIR = Path(__file__).parent.parent / "profiles"


# ─── Rule & Profile Loading ──────────────────────────────────────────────────


def load_rules(rules_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load rule configurations from rules/ directory.

    Falls back to built-in defaults if rules directory or files are not found.
    """
    rules_path = Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR
    rules = {}

    rule_files = {
        "text-consistency": "text-consistency.json",
        "layout-anomaly": "layout-anomaly.json",
        "dom-ocr-crossval": "dom-ocr-crossval.json",
        "accessibility": "accessibility.json",
        "i18n": "i18n.json",
        "dynamic-content": "dynamic-content.json",
    }

    for key, filename in rule_files.items():
        filepath = rules_path / filename
        if filepath.exists():
            rules[key] = json.loads(filepath.read_text())
        else:
            rules[key] = _get_builtin_default(key)

    return rules


def _get_builtin_default(rule_name: str) -> Dict[str, Any]:
    """Return built-in default rules if JSON file is not found."""
    defaults = {
        "text-consistency": {
            "version": "1.0",
            "default_strategy": "substring",
            "max_results_per_check": 10,
            "ignore_patterns": [],
        },
        "layout-anomaly": {
            "version": "1.0",
            "overflow": {"enabled": True, "severity": "warning"},
            "full_page_text": {
                "enabled": True,
                "width_threshold": 0.95,
                "height_threshold": 0.8,
                "severity": "warning",
            },
            "element_overlap": {"enabled": False, "iou_threshold": 0.3},
            "touch_target_size": {
                "enabled": False,
                "min_width_px": 44,
                "min_height_px": 44,
            },
        },
        "dom-ocr-crossval": {
            "version": "1.0",
            "fuzzy_match": {
                "enabled": True,
                "threshold": 0.6,
                "warning_threshold": 0.7,
            },
            "count_mismatch": {
                "enabled": True,
                "delta_threshold": 0.3,
                "min_elements": 5,
            },
            "dom_not_rendered": {"max_results": 10, "severity": "error"},
            "rendered_not_in_dom": {"max_results": 10, "severity": "warning"},
            "ignore_patterns": ["^[\\s\\u200b\\u200c\\u200d]+$"],
        },
        "accessibility": {
            "version": "1.0",
            "missing_alt": {
                "enabled": True,
                "roles": ["image", "graphic", "img"],
                "ignore_values": ["", "image", "icon"],
                "severity": "error",
            },
            "missing_label": {
                "enabled": False,
                "roles": ["button", "textbox", "checkbox", "radio", "combobox"],
                "severity": "error",
            },
            "canvas_rendered_text": {"enabled": False, "severity": "warning"},
            "emoji_as_icon": {"enabled": False, "severity": "warning"},
        },
        "i18n": {
            "version": "1.0",
            "languages": {
                "zh": {"script_pattern": "[\\u4e00-\\u9fff]"},
                "en": {"script_pattern": "[a-zA-Z]{4,}"},
            },
            "common_false_positives": ["OK", "Login", "API", "URL", "ID"],
        },
        "dynamic-content": {
            "version": "1.0",
            "max_tracked_changes": 5,
        },
    }
    return defaults.get(rule_name, {})


def load_profile(profile_name: str) -> Dict[str, Any]:
    """Load industry profile configuration."""
    profile_path = DEFAULT_PROFILES_DIR / f"{profile_name}.json"
    if not profile_path.exists():
        available = list_available_profiles()
        raise ValueError(
            f"Unknown profile: {profile_name}. Available: {', '.join(available) if available else 'none'}"
        )
    return json.loads(profile_path.read_text())


def list_available_profiles() -> List[str]:
    """List available profile names."""
    if not DEFAULT_PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in DEFAULT_PROFILES_DIR.glob("*.json"))


def apply_rule_overrides(rules: Dict, overrides: Dict) -> Dict:
    """Apply dot-notation rule overrides from a profile.

    Example: {"dom-ocr-crossval.fuzzy_match.enabled": True}
    """
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        target = rules
        for part in parts[:-1]:
            if part in target:
                target = target[part]
            else:
                break
        else:
            if parts[-1] in target:
                target[parts[-1]] = value
    return rules


# ─── OCR Client ──────────────────────────────────────────────────────────────


class PaddleOCRClient:
    """Client for PaddleOCR-VL via SiliconFlow API.

    PaddleOCR-VL outputs text interleaved with <|LOC_xxx|> tags.
    This client parses that format and converts LOC values to pixel coordinates.
    """

    def __init__(self, api_key: str, model: str, api_url: str):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url

    @staticmethod
    def parse_loc_response(
        content: str, image_size: Tuple[int, int]
    ) -> List[Dict[str, Any]]:
        """Parse PaddleOCR-VL native output format.

        The model outputs text followed by <|LOC_xxx|> tags for coordinates.
        LOC values are normalized and must be scaled to pixel coordinates.
        """
        img_width, img_height = image_size

        text_coord_pairs = re.findall(r"([^\|<]+?)((?:<\|LOC_\d+\|\>)+)", content)

        if not text_coord_pairs:
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            return [{"text": line, "box": []} for line in lines]

        all_loc_values = []
        for _, loc_tags in text_coord_pairs:
            coords = [int(c) for c in re.findall(r"LOC_(\d+)", loc_tags)]
            all_loc_values.extend(coords)

        max_loc = max(all_loc_values) if all_loc_values else 972

        x_scale = img_width / max_loc if max_loc > 0 else 1
        y_scale = img_height / max_loc if max_loc > 0 else 1

        texts = []
        for text_chunk, loc_tags in text_coord_pairs:
            text = text_chunk.strip()
            if not text:
                continue

            coord_matches = re.findall(r"LOC_(\d+)", loc_tags)
            coords = [int(c) for c in coord_matches]

            if len(coords) >= 8:
                box = []
                for i in range(0, 8, 2):
                    x = int(coords[i] * x_scale)
                    y = int(coords[i + 1] * y_scale)
                    box.append([x, y])
            elif len(coords) >= 4:
                x1 = int(coords[0] * x_scale)
                y1 = int(coords[1] * y_scale)
                x2 = int(coords[2] * x_scale)
                y2 = int(coords[3] * y_scale)
                box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                box = []

            texts.append({"text": text, "box": box})

        return texts

    async def recognize(
        self, image_path: str, prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send image to PaddleOCR and get text + coordinates."""
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_url)

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime = mime_map.get(ext, "image/png")

        user_prompt = prompt or "OCR"

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            max_tokens=4000,
            temperature=0,
        )

        content = response.choices[0].message.content or ""

        with Image.open(image_path) as img:
            image_size = img.size

        # Check if model returned placeholder characters instead of real text
        placeholder_chars = set("☐□📧📝")
        real_text = [
            c for c in content if c not in placeholder_chars and not c.isspace()
        ]
        if content and not real_text:
            # Model returned only placeholders - fallback: use content as-is line by line
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            texts = [{"text": line, "box": []} for line in lines]
        else:
            texts = self.parse_loc_response(content, image_size)

        return {
            "texts": texts,
            "full_text": "\n".join(t["text"] for t in texts),
        }


# ─── Accessibility Tree Parser ───────────────────────────────────────────────


def parse_a11y_tree(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten accessibility tree into a list of elements with text and position.

    Only extracts text from leaf nodes to avoid duplicate/concatenated text
    from parent elements that include all their children's textContent.
    """
    elements = []

    def walk(node: Dict[str, Any], path: str = ""):
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        bounds = node.get("bounds", {})
        children = node.get("children", [])

        text = name or value or ""
        text = text.strip()

        # Only add text from leaf nodes (no children or only generic children)
        # to avoid duplicate text from parent elements
        is_leaf = len(children) == 0
        if is_leaf and text:
            elements.append(
                {
                    "role": role,
                    "text": text,
                    "bounds": bounds,
                    "path": path,
                }
            )

        for i, child in enumerate(children):
            child_path = f"{path}/{role}[{i}]" if path else f"{role}[{i}]"
            walk(child, child_path)

    if tree:
        walk(tree)
    return elements


# ─── Test Levels ─────────────────────────────────────────────────────────────


class UITestEngine:
    """Execute UI test levels L1-L6 with data-driven rules."""

    def __init__(
        self,
        ocr_result: Dict,
        a11y_elements: List[Dict],
        config: Dict[str, Any],
        image_size: Tuple[int, int],
        rules: Optional[Dict[str, Any]] = None,
    ):
        self.ocr_texts = ocr_result.get("texts", [])
        self.a11y_elements = a11y_elements
        self.config = config
        self.image_size = image_size
        self.rules = rules or {}
        self.results: List[Dict[str, Any]] = []

    def _add_result(
        self,
        level: str,
        issue_type: str,
        severity: str,
        element: str,
        expected: str,
        actual: str,
        region: Optional[List] = None,
        suggestion: str = "",
    ):
        self.results.append(
            {
                "type": issue_type,
                "level": level,
                "severity": severity,
                "element": element,
                "expected": expected,
                "actual": actual,
                "screenshot_region": region,
                "suggestion": suggestion,
            }
        )

    def run_l1_text_consistency(self):
        """L1: Verify visible text matches expected values from config."""
        rules = self.rules.get("text-consistency", {})
        strategy = rules.get("default_strategy", "substring")
        max_results = rules.get("max_results_per_check", 10)
        ignore_patterns = rules.get("ignore_patterns", [])

        ignore_res = [re.compile(p) for p in ignore_patterns]

        expected_texts = self.config.get("expected_texts", {})
        for element_name, expected_text in expected_texts.items():
            if any(p.search(expected_text) for p in ignore_res):
                continue

            matched = False
            for ocr_item in self.ocr_texts:
                ocr_text = ocr_item.get("text", "")
                if strategy == "exact":
                    if expected_text == ocr_text:
                        matched = True
                        break
                elif strategy == "substring":
                    if expected_text in ocr_text:
                        matched = True
                        break
                elif strategy == "fuzzy":
                    threshold = (
                        rules.get("match_strategies", {})
                        .get("fuzzy", {})
                        .get("threshold", 0.8)
                    )
                    sim = self._text_similarity(expected_text, ocr_text)
                    if sim >= threshold:
                        matched = True
                        break

            if not matched:
                actual_texts = [t["text"] for t in self.ocr_texts[:max_results]]
                self._add_result(
                    level="L1",
                    issue_type="text_missing",
                    severity="error",
                    element=element_name,
                    expected=expected_text,
                    actual=f"Not found. Nearby texts: {', '.join(actual_texts)}",
                    suggestion="Check if the element is rendered or if text content changed",
                )

    def run_l2_layout_reasonableness(self):
        """L2: Detect layout anomalies from OCR box coordinates."""
        rules = self.rules.get("layout-anomaly", {})
        img_w, img_h = self.image_size

        for i, item in enumerate(self.ocr_texts):
            box = item.get("box", [])
            if len(box) != 4:
                continue
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            x_min, x_max = min(x_coords), max(x_coords)
            y_min, y_max = min(y_coords), max(y_coords)
            width = x_max - x_min
            height = y_max - y_min

            if rules.get("overflow", {}).get("enabled", True):
                if x_max > img_w or y_max > img_h:
                    self._add_result(
                        level="L2",
                        issue_type="overflow",
                        severity=rules["overflow"].get("severity", "warning"),
                        element=f"text_region_{i}",
                        expected=f"within {img_w}x{img_h}",
                        actual=f"extends to ({x_max}, {y_max})",
                        region=box,
                        suggestion="Check container overflow settings or viewport size",
                    )

            fp_rules = rules.get("full_page_text", {})
            if fp_rules.get("enabled", True):
                w_thresh = fp_rules.get("width_threshold", 0.95)
                h_thresh = fp_rules.get("height_threshold", 0.8)
                if width > img_w * w_thresh and height > img_h * h_thresh:
                    self._add_result(
                        level="L2",
                        issue_type="possible_full_page_text",
                        severity=fp_rules.get("severity", "warning"),
                        element=f"text_region_{i}",
                        expected="normal text block",
                        actual=f"spans {width}x{height} ({width / img_w * 100:.0f}% width)",
                        region=box,
                        suggestion="Verify this is not a rendering artifact",
                    )

        if rules.get("element_overlap", {}).get("enabled", False):
            self._check_element_overlap(rules["element_overlap"])

        if rules.get("touch_target_size", {}).get("enabled", False):
            self._check_touch_target_size(rules["touch_target_size"])

    def _check_element_overlap(self, config: Dict):
        """Check for overlapping OCR text regions."""
        threshold = config.get("iou_threshold", 0.3)
        boxes = []
        for item in self.ocr_texts:
            box = item.get("box", [])
            if len(box) == 4:
                boxes.append((item["text"], box))

        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                iou = self._calculate_iou(boxes[i][1], boxes[j][1])
                if iou > threshold:
                    self._add_result(
                        level="L2",
                        issue_type="element_overlap",
                        severity=config.get("severity", "warning"),
                        element=f"{boxes[i][0][:30]} / {boxes[j][0][:30]}",
                        expected="No overlapping text regions",
                        actual=f"IoU: {iou:.2f} (threshold: {threshold})",
                        region=boxes[i][1],
                        suggestion="Check for overlapping elements or z-index issues",
                    )

    def _check_touch_target_size(self, config: Dict):
        """Check interactive elements meet minimum touch target size."""
        min_w = config.get("min_width_px", 44)
        min_h = config.get("min_height_px", 44)
        interactive_roles = {"button", "link", "combobox", "tab"}

        for elem in self.a11y_elements:
            if elem["role"] in interactive_roles:
                b = elem.get("bounds", {})
                w, h = b.get("width", 0), b.get("height", 0)
                if (w > 0 and w < min_w) or (h > 0 and h < min_h):
                    self._add_result(
                        level="L2",
                        issue_type="touch_target_too_small",
                        severity=config.get("severity", "warning"),
                        element=f"{elem['role']}: {elem.get('text', '')[:30]}",
                        expected=f">= {min_w}x{min_h}px",
                        actual=f"{w}x{h}px",
                        suggestion="Increase touch target size (min 44x44pt for accessibility)",
                    )

    @staticmethod
    def _calculate_iou(box1: List, box2: List) -> float:
        """Calculate Intersection over Union for two 4-point boxes."""
        x1_min = min(p[0] for p in box1)
        y1_min = min(p[1] for p in box1)
        x1_max = max(p[0] for p in box1)
        y1_max = max(p[1] for p in box1)

        x2_min = min(p[0] for p in box2)
        y2_min = min(p[1] for p in box2)
        x2_max = max(p[0] for p in box2)
        y2_max = max(p[1] for p in box2)

        inter_x = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
        inter_y = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
        inter_area = inter_x * inter_y

        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def run_l3_dom_consistency(self):
        """L3: Cross-reference OCR vs DOM/A11y Tree content."""
        rules = self.rules.get("dom-ocr-crossval", {})
        fuzzy_enabled = rules.get("fuzzy_match", {}).get("enabled", False)
        fuzzy_threshold = rules.get("fuzzy_match", {}).get("threshold", 0.6)
        warn_threshold = rules.get("fuzzy_match", {}).get("warning_threshold", 0.7)
        ignore_patterns = rules.get("ignore_patterns", [])

        ignore_res = [re.compile(p) for p in ignore_patterns]

        ocr_text_set = {
            t["text"].strip() for t in self.ocr_texts if t.get("text", "").strip()
        }
        a11y_text_set = {
            e["text"].strip() for e in self.a11y_elements if e.get("text", "").strip()
        }

        if fuzzy_enabled:
            matched_a11y = set()
            for a11y_text in a11y_text_set:
                if any(p.search(a11y_text) for p in ignore_res):
                    continue
                if a11y_text in ocr_text_set:
                    matched_a11y.add(a11y_text)
                    continue

                best_match, similarity = self._find_best_match(
                    a11y_text, list(ocr_text_set), threshold=fuzzy_threshold
                )
                if best_match and similarity >= fuzzy_threshold:
                    matched_a11y.add(a11y_text)
                    if similarity < warn_threshold:
                        self._add_result(
                            level="L3",
                            issue_type="text_mismatch",
                            severity="warning",
                            element="unknown",
                            expected=f"Text '{a11y_text}'",
                            actual=f"Closest OCR match: '{best_match}' (similarity: {similarity:.2f})",
                            suggestion="Possible typo or rendering issue",
                        )

            in_a11y_not_ocr = a11y_text_set - matched_a11y
        else:
            in_a11y_not_ocr = a11y_text_set - ocr_text_set

        max_results = rules.get("dom_not_rendered", {}).get("max_results", 10)
        for text in list(in_a11y_not_ocr)[:max_results]:
            if any(p.search(text) for p in ignore_res):
                continue
            self._add_result(
                level="L3",
                issue_type="dom_not_rendered",
                severity=rules.get("dom_not_rendered", {}).get("severity", "error"),
                element="unknown",
                expected=f"Text '{text}' should be visible",
                actual="Not detected in screenshot by OCR",
                suggestion="Element may be hidden, off-screen, or have visibility:hidden",
            )

        max_results_dom = rules.get("rendered_not_in_dom", {}).get("max_results", 10)
        in_ocr_not_a11y = ocr_text_set - a11y_text_set
        for text in list(in_ocr_not_a11y)[:max_results_dom]:
            self._add_result(
                level="L3",
                issue_type="rendered_not_in_dom",
                severity=rules.get("rendered_not_in_dom", {}).get(
                    "severity", "warning"
                ),
                element="unknown",
                expected="All visible text should be in DOM",
                actual=f"Text '{text}' visible but not in accessibility tree",
                suggestion="May be canvas-rendered text or missing ARIA label",
            )

        count_rules = rules.get("count_mismatch", {})
        if count_rules.get("enabled", True):
            a11y_count = len(a11y_text_set)
            ocr_count = len(ocr_text_set)
            delta_thresh = count_rules.get("delta_threshold", 0.3)
            min_elements = count_rules.get("min_elements", 5)
            if (
                abs(a11y_count - ocr_count) > max(a11y_count, ocr_count) * delta_thresh
                and a11y_count > min_elements
            ):
                self._add_result(
                    level="L3",
                    issue_type="count_mismatch",
                    severity=count_rules.get("severity", "warning"),
                    element="page",
                    expected=f"~{a11y_count} text elements in DOM",
                    actual=f"{ocr_count} text regions in screenshot",
                    suggestion="Large discrepancy may indicate rendering issues or hidden content",
                )

    def run_l4_accessibility(self):
        """L4: Joint OCR + A11y accessibility analysis."""
        rules = self.rules.get("accessibility", {})

        if rules.get("missing_alt", {}).get("enabled", True):
            alt_rules = rules["missing_alt"]
            roles = alt_rules.get("roles", ["image", "graphic", "img"])
            ignore_values = alt_rules.get("ignore_values", ["", "image", "icon"])
            for elem in self.a11y_elements:
                if elem["role"] in roles:
                    if not elem.get("text") or elem["text"] in ignore_values:
                        self._add_result(
                            level="L4",
                            issue_type="missing_alt",
                            severity=alt_rules.get("severity", "error"),
                            element=f"{elem['role']} at {elem.get('path', 'unknown')}",
                            expected="Descriptive alt text",
                            actual=elem.get("text", "(empty)"),
                            suggestion="Add meaningful alt attribute to image",
                        )

        if rules.get("missing_label", {}).get("enabled", False):
            label_rules = rules["missing_label"]
            interactive_roles = label_rules.get(
                "roles", ["button", "textbox", "checkbox", "radio", "combobox"]
            )
            for elem in self.a11y_elements:
                if elem["role"] in interactive_roles and not elem.get("text"):
                    self._add_result(
                        level="L4",
                        issue_type="missing_label",
                        severity=label_rules.get("severity", "error"),
                        element=f"{elem['role']} at {elem.get('path', 'unknown')}",
                        expected="Accessible label or aria-label",
                        actual="No accessible name",
                        suggestion="Add aria-label or visible label for screen readers",
                    )

        if rules.get("canvas_rendered_text", {}).get("enabled", False):
            a11y_texts = {e["text"] for e in self.a11y_elements if e.get("text")}
            for item in self.ocr_texts:
                text = item.get("text", "").strip()
                if text and text not in a11y_texts and item.get("box"):
                    self._add_result(
                        level="L4",
                        issue_type="canvas_rendered_text",
                        severity=rules["canvas_rendered_text"].get(
                            "severity", "warning"
                        ),
                        element=f"text at {item['box']}",
                        expected="Text should be in accessibility tree",
                        actual=f"Text '{text[:50]}' only visible via OCR",
                        region=item["box"],
                        suggestion="Text may be canvas-rendered or missing ARIA label",
                    )

    def run_l5_internationalization(self):
        """L5: Detect language mismatches."""
        rules = self.rules.get("i18n", {})
        expected_lang = self.config.get("expected_language", "")
        if not expected_lang:
            return

        languages = rules.get("languages", {})
        lang_config = languages.get(expected_lang)
        if not lang_config:
            return

        lang_pattern = re.compile(lang_config["script_pattern"])
        false_positives = set(rules.get("common_false_positives", []))

        other_langs = {k: v for k, v in languages.items() if k != expected_lang}

        for item in self.ocr_texts:
            text = item.get("text", "").strip()
            if not text or text in false_positives:
                continue

            has_expected = bool(lang_pattern.search(text))

            for other_code, other_config in other_langs.items():
                other_pattern = re.compile(other_config["script_pattern"])
                if other_pattern.search(text) and not has_expected:
                    self._add_result(
                        level="L5",
                        issue_type="unexpected_language",
                        severity="warning",
                        element="text_region",
                        expected=f"{expected_lang} text",
                        actual=f"{other_code} text found: '{text[:50]}'",
                        region=item.get("box"),
                        suggestion=f"Check locale configuration - expected {expected_lang}, found {other_code}",
                    )

    def run_l6_dynamic_content(self, before_ocr: Dict, after_ocr: Dict):
        """L6: Compare screenshot sequences for state transitions."""
        rules = self.rules.get("dynamic-content", {})
        max_changes = rules.get("max_tracked_changes", 5)

        before_texts = {t["text"] for t in before_ocr.get("texts", [])}
        after_texts = {t["text"] for t in after_ocr.get("texts", [])}

        removed = before_texts - after_texts
        added = after_texts - before_texts

        for text in list(removed)[:max_changes]:
            self._add_result(
                level="L6",
                issue_type="content_removed",
                severity="info",
                element="dynamic",
                expected="Text persists",
                actual=f"Text '{text[:50]}' no longer visible",
                suggestion="Expected for loading states; verify if intended",
            )

        for text in list(added)[:max_changes]:
            self._add_result(
                level="L6",
                issue_type="content_added",
                severity="info",
                element="dynamic",
                expected="No new content",
                actual=f"New text: '{text[:50]}'",
                suggestion="Verify new content is expected after interaction",
            )

    def run(
        self,
        levels: List[str],
        before_ocr: Optional[Dict] = None,
        after_ocr: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Execute specified test levels."""
        level_map = {
            "L1": self.run_l1_text_consistency,
            "L2": self.run_l2_layout_reasonableness,
            "L3": self.run_l3_dom_consistency,
            "L4": self.run_l4_accessibility,
            "L5": self.run_l5_internationalization,
        }

        for level in levels:
            if level in level_map:
                level_map[level]()
            elif level == "L6":
                if before_ocr and after_ocr:
                    self.run_l6_dynamic_content(before_ocr, after_ocr)

        return self.results

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """LCS-based text similarity (0.0-1.0)."""
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.8
        if not a or not b:
            return 0.0
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        return dp[m][n] / max(m, n)

    @staticmethod
    def _find_best_match(
        query: str, candidates: List[str], threshold: float = 0.6
    ) -> Tuple[Optional[str], float]:
        """Find the best matching candidate text."""
        best = None
        best_score = 0.0
        for c in candidates:
            score = UITestEngine._text_similarity(query, c)
            if score > best_score:
                best_score = score
                best = c
        if best_score >= threshold:
            return best, best_score
        return None, best_score


# ─── Report Generator ────────────────────────────────────────────────────────


class ReportGenerator:
    """Generate JSON and Markdown reports."""

    def __init__(
        self,
        url: str,
        results: List[Dict],
        output_dir: str,
        image_size: Tuple[int, int],
        duration: float,
    ):
        self.url = url
        self.results = results
        self.output_dir = Path(output_dir)
        self.image_size = image_size
        self.duration = duration
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _summary(self) -> Dict[str, int]:
        summary = {"total": len(self.results), "error": 0, "warning": 0, "info": 0}
        for r in self.results:
            sev = r.get("severity", "info")
            if sev in summary:
                summary[sev] += 1
        return summary

    def generate_json(self) -> str:
        """Generate structured JSON report."""
        summary = self._summary()
        report = {
            "test_id": f"ui-test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
            "url": self.url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_size": list(self.image_size),
            "duration_seconds": round(self.duration, 2),
            "summary": {
                "total_checks": summary["total"],
                "passed": summary["total"] - summary["error"] - summary["warning"],
                "failed": summary["error"],
                "warnings": summary["warning"],
                "info": summary["info"],
            },
            "results": self.results,
        }
        path = self.output_dir / "report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        return str(path)

    def generate_markdown(self) -> str:
        """Generate human-readable Markdown report."""
        summary = self._summary()
        errors = [r for r in self.results if r["severity"] == "error"]
        warnings = [r for r in self.results if r["severity"] == "warning"]
        infos = [r for r in self.results if r["severity"] == "info"]

        lines = [
            f"# UI Test Report — {self.url}",
            "",
            f"| Item | Value |",
            f"|------|-------|",
            f"| URL | {self.url} |",
            f"| Time | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |",
            f"| Image Size | {self.image_size[0]}x{self.image_size[1]} |",
            f"| Duration | {self.duration:.1f}s |",
            f"| Checks | {summary['total']} total "
            f"(✅ {summary['total'] - summary['error'] - summary['warning']} "
            f"❌ {summary['error']} ⚠️ {summary['warning']}) |",
            "",
        ]

        if errors:
            lines.append("## ❌ Errors\n")
            for i, r in enumerate(errors, 1):
                lines.append(f"**{i}. [{r['level']}] {r['type']}** — {r['element']}")
                lines.append(f"- Expected: `{r['expected']}`")
                lines.append(f"- Actual: `{r['actual']}`")
                if r.get("suggestion"):
                    lines.append(f"- Suggestion: {r['suggestion']}")
                lines.append("")

        if warnings:
            lines.append("## ⚠️ Warnings\n")
            for i, r in enumerate(warnings, 1):
                lines.append(f"**{i}. [{r['level']}] {r['type']}** — {r['element']}")
                lines.append(f"- Expected: `{r['expected']}`")
                lines.append(f"- Actual: `{r['actual']}`")
                if r.get("suggestion"):
                    lines.append(f"- Suggestion: {r['suggestion']}")
                lines.append("")

        if infos:
            lines.append("## ℹ️ Info\n")
            for i, r in enumerate(infos, 1):
                lines.append(f"**{i}. [{r['level']}] {r['type']}**: {r['actual']}")
                lines.append("")

        if not self.results:
            lines.append("## ✅ All checks passed\n")

        path = self.output_dir / "report.md"
        path.write_text("\n".join(lines))
        return str(path)


# ─── Main ────────────────────────────────────────────────────────────────────

A11Y_TREE_SCRIPT = """() => {
    function buildA11yTree(node, depth = 0) {
        if (depth > 20) return null;
        const role = node.getAttribute('role') ||
            (node.tagName === 'BUTTON' ? 'button' : '') ||
            (node.tagName === 'INPUT' ? 'textbox' : '') ||
            (node.tagName === 'IMG' ? 'img' : '') ||
            (node.tagName === 'A' ? 'link' : '') ||
            (node.tagName === 'H1' ? 'heading' : '') ||
            (node.tagName === 'H2' ? 'heading' : '') ||
            (node.tagName === 'H3' ? 'heading' : '') ||
            (node.tagName === 'H4' ? 'heading' : '') ||
            (node.tagName === 'H5' ? 'heading' : '') ||
            (node.tagName === 'H6' ? 'heading' : '') ||
            (node.tagName === 'NAV' ? 'navigation' : '') ||
            (node.tagName === 'MAIN' ? 'main' : '') ||
            (node.tagName === 'HEADER' ? 'banner' : '') ||
            (node.tagName === 'FOOTER' ? 'contentinfo' : '') ||
            node.tagName?.toLowerCase() || '';
        const name = node.getAttribute('aria-label') ||
            node.getAttribute('alt') ||
            node.textContent?.trim().substring(0, 200) || '';
        const rect = node.getBoundingClientRect();
        const result = {
            role: role || 'generic',
            name: name,
            bounds: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            tagName: node.tagName,
            visible: rect.width > 0 && rect.height > 0
        };
        const children = [];
        for (const child of node.children) {
            const childTree = buildA11yTree(child, depth + 1);
            if (childTree) children.push(childTree);
        }
        if (children.length) result.children = children;
        return result;
    }
    return buildA11yTree(document.body);
}"""


async def execute_actions(page, actions_str: str) -> None:
    """Parse and execute an action sequence.

    Supported actions:
    - click(selector)
    - wait(milliseconds)
    - type(selector, "text")
    - screenshot (no-op, handled by caller)
    """
    actions = actions_str.split(";")
    for action in actions:
        action = action.strip()
        if not action:
            continue
        if action.startswith("click("):
            selector = action[6:-1]
            print(f"  Clicking: {selector}")
            await page.click(selector)
        elif action.startswith("wait("):
            ms = int(action[5:-1])
            print(f"  Waiting: {ms}ms")
            await page.wait_for_timeout(ms)
        elif action.startswith("type("):
            inner = action[5:-1]
            comma_idx = inner.find(",")
            if comma_idx != -1:
                selector = inner[:comma_idx].strip()
                text = inner[comma_idx + 1 :].strip().strip('"').strip("'")
                print(f"  Typing '{text}' into: {selector}")
                await page.fill(selector, text)
        elif action == "screenshot":
            pass
        else:
            print(f"  Unknown action: {action}")


async def run_test(args) -> None:
    """Execute the full UI test pipeline."""
    start_time = time.time()

    sys.path.insert(0, str(Path(__file__).parent))

    if not PADDLEOCR_API_KEY:
        print("Error: PADDLEOCR_API_KEY or SILICONFLOW_API_KEY not set")
        sys.exit(1)

    ocr_client = PaddleOCRClient(
        api_key=PADDLEOCR_API_KEY,
        model=PADDLEOCR_MODEL,
        api_url=PADDLEOCR_API_URL,
    )

    config = {}
    if args.config:
        config = json.loads(Path(args.config).read_text())

    rules = load_rules(args.rules)

    profile = {}
    if args.profile:
        profile = load_profile(args.profile)
        print(f"Using profile: {args.profile} ({profile.get('description', '')})")
        if profile.get("rule_overrides"):
            rules = apply_rule_overrides(rules, profile["rule_overrides"])

    levels = config.get("levels", profile.get("default_levels"))
    if args.levels:
        levels = args.levels.split(",")
    if not levels:
        levels = ["L1", "L3"]

    viewport_str = args.viewport or profile.get("viewport", "1280x720")
    viewport = tuple(map(int, viewport_str.split("x")))

    wait_ms = config.get("wait_ms", profile.get("wait_ms", args.wait))

    screenshot_path = Path(args.output) / "screenshot.png"
    Path(args.output).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": viewport[0], "height": viewport[1]}
        )

        print(f"Navigating to {args.url} ...")
        await page.goto(args.url, wait_until="networkidle")
        await page.wait_for_timeout(wait_ms)

        print("Capturing screenshot ...")
        await page.screenshot(path=str(screenshot_path), full_page=True)

        print("Extracting accessibility tree ...")
        a11y_tree = await page.evaluate(A11Y_TREE_SCRIPT)
        a11y_elements = parse_a11y_tree(a11y_tree or {})

        img = Image.open(screenshot_path)
        image_size = img.size

        print(f"Sending screenshot to PaddleOCR ({image_size[0]}x{image_size[1]}) ...")
        ocr_result = await ocr_client.recognize(str(screenshot_path))

        before_ocr = None
        after_ocr = None
        if "L6" in levels and args.actions:
            before_ocr = ocr_result
            print(f"Executing actions: {args.actions} ...")
            await execute_actions(page, args.actions)

            print("Capturing after-action screenshot ...")
            after_screenshot_path = Path(args.output) / "screenshot_after.png"
            await page.screenshot(path=str(after_screenshot_path), full_page=True)

            print("Running after-action OCR ...")
            after_ocr = await ocr_client.recognize(str(after_screenshot_path))

        print(f"Running test levels: {', '.join(levels)} ...")
        engine = UITestEngine(
            ocr_result=ocr_result,
            a11y_elements=a11y_elements,
            config=config,
            image_size=image_size,
            rules=rules,
        )
        results = engine.run(levels, before_ocr=before_ocr, after_ocr=after_ocr)

        if args.baseline:
            from baseline_diff import create_baseline

            baseline_data = create_baseline(
                ocr_result=ocr_result,
                a11y_elements=a11y_elements,
                url=args.url,
                viewport=viewport_str,
                image_size=image_size,
                summary={"total": len(results), "error": 0, "warning": 0, "info": 0},
            )
            baseline_path = Path(args.output) / "baseline.json"
            baseline_path.write_text(
                json.dumps(baseline_data, indent=2, ensure_ascii=False)
            )
            print(f"  Baseline saved: {baseline_path}")

        if args.baseline_file:
            baseline_data = json.loads(Path(args.baseline_file).read_text())
            from baseline_diff import BaselineDiff

            diff_engine = BaselineDiff(
                current_ocr=ocr_result,
                current_a11y=a11y_elements,
                baseline_data=baseline_data,
                threshold=args.diff_threshold,
                image_size=image_size,
            )
            diff_results = diff_engine.run()
            results.extend(diff_results)
            print(f"  Baseline diff: {len(diff_results)} issues found")

        duration = time.time() - start_time

        print(f"Generating reports to {args.output} ...")
        reporter = ReportGenerator(
            url=args.url,
            results=results,
            output_dir=args.output,
            image_size=image_size,
            duration=duration,
        )

        if args.format in ("json", "both"):
            json_path = reporter.generate_json()
            print(f"  JSON report: {json_path}")

        if args.format in ("markdown", "both"):
            md_path = reporter.generate_markdown()
            print(f"  Markdown report: {md_path}")

        if args.annotate:
            from annotate_screenshot import annotate_screenshot

            annotated_path = Path(args.output) / "annotated.png"
            annotate_screenshot(str(screenshot_path), results, str(annotated_path))
            print(f"  Annotated screenshot: {annotated_path}")

        if args.source_map:
            from scripts.source_map_lookup import resolve_issues

            resolved = resolve_issues(results, a11y_elements, args.source_map)
            for i, issue in enumerate(resolved):
                if i < len(results):
                    results[i]["source_location"] = issue.get("source_location", {})

        summary = reporter._summary()
        print(
            f"\nDone in {duration:.1f}s — "
            f"{summary['total']} checks: "
            f"❌ {summary['error']} errors, "
            f"⚠️ {summary['warning']} warnings, "
            f"ℹ️ {summary['info']} info"
        )

        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="PaddleOCR UI Test")
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument("--config", help="Test config JSON file")
    parser.add_argument(
        "--levels",
        default=None,
        help="Test levels (L1-L6, comma-separated). Overrides profile/config.",
    )
    parser.add_argument("--viewport", default=None, help="Viewport size WxH")
    parser.add_argument("--wait", type=int, default=2000, help="Wait ms after load")
    parser.add_argument("--output", default="./test-results", help="Output directory")
    parser.add_argument(
        "--format", choices=["json", "markdown", "both"], default="both"
    )
    parser.add_argument("--source-map", help="Source map directory")
    parser.add_argument(
        "--annotate", action="store_true", help="Generate annotated screenshot"
    )

    parser.add_argument("--rules", help="Rules directory (default: rules/)")
    parser.add_argument(
        "--profile",
        help=f"Industry profile: {', '.join(list_available_profiles()) if list_available_profiles() else 'see profiles/'}",
    )
    parser.add_argument(
        "--baseline", action="store_true", help="Save current run as baseline"
    )
    parser.add_argument(
        "--baseline-file", help="Path to baseline JSON file for regression diff"
    )
    parser.add_argument(
        "--diff-threshold",
        type=float,
        default=0.1,
        help="Layout shift threshold (ratio of max dimension)",
    )
    parser.add_argument(
        "--actions",
        help="Action sequence: 'click(#btn);wait(2000);screenshot'",
    )

    args = parser.parse_args()
    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
