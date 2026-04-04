#!/usr/bin/env python3
"""
Annotate screenshot with issue markers from UI test results.

Draws colored bounding boxes and labels on the screenshot for each detected issue.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


COLOR_MAP = {
    "error": (255, 0, 0, 200),
    "warning": (255, 165, 0, 200),
    "info": (0, 128, 255, 200),
}

LABEL_COLORS = {
    "error": (255, 255, 255),
    "warning": (255, 255, 255),
    "info": (255, 255, 255),
}


def get_font(size: int = 16) -> ImageFont.FreeTypeFont:
    """Get a font for drawing labels, with fallback."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def annotate_screenshot(
    screenshot_path: str,
    results: List[Dict[str, Any]],
    output_path: str,
    label_size: int = 16,
    border_width: int = 3,
) -> str:
    """Draw issue markers on screenshot.

    Args:
        screenshot_path: Path to original screenshot
        results: List of test result dicts with screenshot_region
        output_path: Path to save annotated image
        label_size: Font size for labels
        border_width: Width of bounding box borders

    Returns:
        Path to the annotated image
    """
    img = Image.open(screenshot_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_font(label_size)

    for r in results:
        region = r.get("screenshot_region")
        if not region or len(region) < 4:
            continue

        severity = r.get("severity", "info")
        color = COLOR_MAP.get(severity, (128, 128, 128, 180))
        label_color = LABEL_COLORS.get(severity, (255, 255, 255))

        box = [tuple(p) for p in region[:4]]
        draw.polygon(box, outline=color, width=border_width)

        label = f"[{r.get('level', '?')}] {r.get('type', '?')}"
        top_left = box[0]

        bbox = draw.textbbox(top_left, label, font=font)
        label_w = bbox[2] - bbox[0]
        label_h = bbox[3] - bbox[1]

        label_bg = (
            top_left[0],
            top_left[1] - label_h - 4,
            top_left[0] + label_w + 8,
            top_left[1],
        )

        if label_bg[1] < 0:
            label_bg = (
                top_left[0],
                top_left[1] + 4,
                top_left[0] + label_w + 8,
                top_left[1] + label_h + 8,
            )

        draw.rectangle(label_bg, fill=color)
        draw.text(
            (top_left[0] + 4, label_bg[1] + 2),
            label,
            fill=label_color,
            font=font,
        )

    annotated = Image.alpha_composite(img, overlay)
    annotated = annotated.convert("RGB")
    annotated.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Annotate screenshot with issue markers")
    parser.add_argument("--screenshot", required=True, help="Path to screenshot")
    parser.add_argument("--results", required=True, help="Path to report.json")
    parser.add_argument("--output", default=None, help="Output path (default: annotated.png)")
    parser.add_argument("--label-size", type=int, default=16, help="Label font size")
    args = parser.parse_args()

    if args.output is None:
        args.output = str(Path(args.screenshot).parent / "annotated.png")

    report = json.loads(Path(args.results).read_text())
    results = report.get("results", [])

    output = annotate_screenshot(args.screenshot, results, args.output, args.label_size)
    print(f"Annotated screenshot saved: {output}")


if __name__ == "__main__":
    main()
