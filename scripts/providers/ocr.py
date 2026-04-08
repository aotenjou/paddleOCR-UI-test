from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple

from PIL import Image


class OCRProvider(Protocol):
    async def recognize(self, image_path: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        ...


class PaddleOCRProvider:
    """OpenAI-compatible OCR provider for PaddleOCR-VL endpoints."""

    name = "paddleocr-vl"
    description = "OpenAI-compatible PaddleOCR-VL provider."
    required_env = ("PADDLEOCR_API_KEY | SILICONFLOW_API_KEY",)

    def __init__(self, *, api_key: str, model: str, api_url: str):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url

    @staticmethod
    def parse_loc_response(content: str, image_size: Tuple[int, int]) -> list[dict]:
        img_width, img_height = image_size
        text_coord_pairs = re.findall(r"([^\|<]+?)((?:<\|LOC_\d+\|>)+)", content)
        if not text_coord_pairs:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            return [{"text": line, "box": []} for line in lines]

        all_loc_values = []
        for _, loc_tags in text_coord_pairs:
            all_loc_values.extend(int(value) for value in re.findall(r"LOC_(\d+)", loc_tags))
        max_loc = max(all_loc_values) if all_loc_values else 972
        x_scale = img_width / max_loc if max_loc > 0 else 1
        y_scale = img_height / max_loc if max_loc > 0 else 1

        texts = []
        for text_chunk, loc_tags in text_coord_pairs:
            text = text_chunk.strip()
            if not text:
                continue
            coords = [int(value) for value in re.findall(r"LOC_(\d+)", loc_tags)]
            if len(coords) >= 8:
                box = []
                for index in range(0, 8, 2):
                    box.append([int(coords[index] * x_scale), int(coords[index + 1] * y_scale)])
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

    async def recognize(self, image_path: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("openai library required. Run: pip install openai") from exc

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_url)
        with open(image_path, "rb") as handle:
            image_b64 = base64.b64encode(handle.read()).decode("utf-8")

        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(Path(image_path).suffix.lower(), "image/png")

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
                        {"type": "text", "text": prompt or "OCR"},
                    ],
                }
            ],
            max_tokens=4000,
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        with Image.open(image_path) as image:
            image_size = image.size

        placeholder_chars = set("☐□📧📝")
        real_text = [char for char in content if char not in placeholder_chars and not char.isspace()]
        if content and not real_text:
            texts = [{"text": line.strip(), "box": []} for line in content.splitlines() if line.strip()]
        else:
            texts = self.parse_loc_response(content, image_size)
        return {
            "texts": texts,
            "full_text": "\n".join(item["text"] for item in texts),
        }


OCR_PROVIDER_REGISTRY = {
    "paddleocr-vl": PaddleOCRProvider,
}


def describe_ocr_provider(provider_name: str) -> Dict[str, Any]:
    provider_cls = OCR_PROVIDER_REGISTRY[provider_name]
    return {
        "name": getattr(provider_cls, "name", provider_name),
        "description": getattr(provider_cls, "description", ""),
        "required_env": list(getattr(provider_cls, "required_env", ())),
    }


def list_ocr_providers(detailed: bool = False) -> list:
    if detailed:
        return [describe_ocr_provider(name) for name in sorted(OCR_PROVIDER_REGISTRY)]
    return sorted(OCR_PROVIDER_REGISTRY)


def create_ocr_provider(
    provider_name: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_url: Optional[str] = None,
) -> OCRProvider:
    provider_cls = OCR_PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown OCR provider: {provider_name}. Available: {', '.join(list_ocr_providers())}"
        )
    return provider_cls(
        api_key=api_key or os.environ.get("PADDLEOCR_API_KEY") or os.environ.get("SILICONFLOW_API_KEY", ""),
        model=model or os.environ.get("PADDLEOCR_MODEL", "PaddlePaddle/PaddleOCR-VL-1.5"),
        api_url=api_url or os.environ.get("PADDLEOCR_API_URL", "https://api.siliconflow.cn/v1"),
    )
