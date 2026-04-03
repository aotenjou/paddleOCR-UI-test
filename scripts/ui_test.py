#!/usr/bin/env python3
"""
PaddleOCR UI Test - Main execution script.

Combines PaddleOCR screenshot analysis with Playwright Accessibility Tree
for intelligent UI testing across 6 levels (L1-L6).

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
    """Execute UI test levels L1-L6."""

    def __init__(
        self,
        ocr_result: Dict,
        a11y_elements: List[Dict],
        config: Dict[str, Any],
        image_size: Tuple[int, int],
    ):
        self.ocr_texts = ocr_result.get("texts", [])
        self.a11y_elements = a11y_elements
        self.config = config
        self.image_size = image_size
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
        expected_texts = self.config.get("expected_texts", {})
        for element_name, expected_text in expected_texts.items():
            matched = False
            for ocr_item in self.ocr_texts:
                if expected_text in ocr_item.get("text", ""):
                    matched = True
                    break
            if not matched:
                actual_texts = [t["text"] for t in self.ocr_texts[:5]]
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

            if x_max > img_w or y_max > img_h:
                self._add_result(
                    level="L2",
                    issue_type="overflow",
                    severity="warning",
                    element=f"text_region_{i}",
                    expected=f"within {img_w}x{img_h}",
                    actual=f"extends to ({x_max}, {y_max})",
                    region=box,
                    suggestion="Check container overflow settings or viewport size",
                )

            if width > img_w * 0.95 and height > img_h * 0.8:
                self._add_result(
                    level="L2",
                    issue_type="possible_full_page_text",
                    severity="warning",
                    element=f"text_region_{i}",
                    expected="normal text block",
                    actual=f"spans {width}x{height} ({width / img_w * 100:.0f}% width)",
                    region=box,
                    suggestion="Verify this is not a rendering artifact",
                )

    def run_l3_dom_consistency(self):
        """L3: Cross-reference OCR vs DOM/A11y Tree content."""
        ocr_text_set = {
            t["text"].strip() for t in self.ocr_texts if t.get("text", "").strip()
        }
        a11y_text_set = {
            e["text"].strip() for e in self.a11y_elements if e.get("text", "").strip()
        }

        in_a11y_not_ocr = a11y_text_set - ocr_text_set
        in_ocr_not_a11y = ocr_text_set - a11y_text_set

        for text in list(in_a11y_not_ocr)[:10]:
            self._add_result(
                level="L3",
                issue_type="dom_not_rendered",
                severity="error",
                element="unknown",
                expected=f"Text '{text}' should be visible",
                actual="Not detected in screenshot by OCR",
                suggestion="Element may be hidden, off-screen, or have visibility:hidden",
            )

        for text in list(in_ocr_not_a11y)[:10]:
            self._add_result(
                level="L3",
                issue_type="rendered_not_in_dom",
                severity="warning",
                element="unknown",
                expected="All visible text should be in DOM",
                actual=f"Text '{text}' visible but not in accessibility tree",
                suggestion="May be canvas-rendered text or missing ARIA label",
            )

        a11y_count = len(a11y_text_set)
        ocr_count = len(ocr_text_set)
        if (
            abs(a11y_count - ocr_count) > max(a11y_count, ocr_count) * 0.3
            and a11y_count > 5
        ):
            self._add_result(
                level="L3",
                issue_type="count_mismatch",
                severity="warning",
                element="page",
                expected=f"~{a11y_count} text elements in DOM",
                actual=f"{ocr_count} text regions in screenshot",
                suggestion="Large discrepancy may indicate rendering issues or hidden content",
            )

    def run_l4_accessibility(self):
        """L4: Joint OCR + A11y accessibility analysis."""
        for elem in self.a11y_elements:
            if elem["role"] in ("image", "graphic", "img"):
                if not elem.get("text") or elem["text"] in ("", "image", "icon"):
                    self._add_result(
                        level="L4",
                        issue_type="missing_alt",
                        severity="error",
                        element=f"{elem['role']} at {elem.get('path', 'unknown')}",
                        expected="Descriptive alt text",
                        actual=elem.get("text", "(empty)"),
                        suggestion="Add meaningful alt attribute to image",
                    )

    def run_l5_internationalization(self):
        """L5: Detect language mismatches."""
        expected_lang = self.config.get("expected_language", "")
        if not expected_lang:
            return

        cn_pattern = re.compile(r"[\u4e00-\u9fff]")
        en_pattern = re.compile(r"[a-zA-Z]{4,}")

        for item in self.ocr_texts:
            text = item.get("text", "")
            has_cn = bool(cn_pattern.search(text))
            has_en = bool(en_pattern.search(text))

            if expected_lang == "zh" and has_en and not has_cn:
                self._add_result(
                    level="L5",
                    issue_type="untranslated_text",
                    severity="warning",
                    element="text_region",
                    expected="Chinese text",
                    actual=f"English text found: '{text[:50]}'",
                    region=item.get("box"),
                    suggestion="Check i18n translation files for missing keys",
                )
            elif expected_lang == "en" and has_cn:
                self._add_result(
                    level="L5",
                    issue_type="unexpected_language",
                    severity="warning",
                    element="text_region",
                    expected="English text",
                    actual=f"Chinese text found: '{text[:50]}'",
                    region=item.get("box"),
                    suggestion="Check locale configuration or fallback language",
                )

    def run_l6_dynamic_content(self, before_ocr: Dict, after_ocr: Dict):
        """L6: Compare screenshot sequences for state transitions."""
        before_texts = {t["text"] for t in before_ocr.get("texts", [])}
        after_texts = {t["text"] for t in after_ocr.get("texts", [])}

        removed = before_texts - after_texts
        added = after_texts - before_texts

        for text in list(removed)[:5]:
            self._add_result(
                level="L6",
                issue_type="content_removed",
                severity="info",
                element="dynamic",
                expected="Text persists",
                actual=f"Text '{text[:50]}' no longer visible",
                suggestion="Expected for loading states; verify if intended",
            )

        for text in list(added)[:5]:
            self._add_result(
                level="L6",
                issue_type="content_added",
                severity="info",
                element="dynamic",
                expected="No new content",
                actual=f"New text: '{text[:50]}'",
                suggestion="Verify new content is expected after interaction",
            )

    def run(self, levels: List[str]) -> List[Dict[str, Any]]:
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

        return self.results


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


async def run_test(args) -> None:
    """Execute the full UI test pipeline."""
    start_time = time.time()

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

    levels = args.levels.split(",") if args.levels else ["L1", "L3"]
    viewport = (
        tuple(map(int, args.viewport.split("x"))) if args.viewport else (1280, 720)
    )

    screenshot_path = Path(args.output) / "screenshot.png"
    Path(args.output).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": viewport[0], "height": viewport[1]}
        )

        print(f"Navigating to {args.url} ...")
        await page.goto(args.url, wait_until="networkidle")
        await page.wait_for_timeout(args.wait)

        print("Capturing screenshot ...")
        await page.screenshot(path=str(screenshot_path), full_page=True)

        print("Extracting accessibility tree ...")
        a11y_tree = await page.evaluate(A11Y_TREE_SCRIPT)
        a11y_elements = parse_a11y_tree(a11y_tree or {})

        img = Image.open(screenshot_path)
        image_size = img.size

        print(f"Sending screenshot to PaddleOCR ({image_size[0]}x{image_size[1]}) ...")
        ocr_result = await ocr_client.recognize(str(screenshot_path))

        print(f"Running test levels: {', '.join(levels)} ...")
        engine = UITestEngine(
            ocr_result=ocr_result,
            a11y_elements=a11y_elements,
            config=config,
            image_size=image_size,
        )
        results = engine.run(levels)

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
        "--levels", default="L1,L3", help="Test levels (L1-L6, comma-separated)"
    )
    parser.add_argument("--viewport", default="1280x720", help="Viewport size WxH")
    parser.add_argument("--wait", type=int, default=2000, help="Wait ms after load")
    parser.add_argument("--output", default="./test-results", help="Output directory")
    parser.add_argument(
        "--format", choices=["json", "markdown", "both"], default="both"
    )
    parser.add_argument("--source-map", help="Source map directory")
    parser.add_argument(
        "--annotate", action="store_true", help="Generate annotated screenshot"
    )
    args = parser.parse_args()

    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
