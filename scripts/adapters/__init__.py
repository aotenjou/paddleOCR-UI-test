"""Input adapters for PaddleOCR UI test."""

from .registry import build_adapter, detect_input_mode, list_adapters

__all__ = ["build_adapter", "detect_input_mode", "list_adapters"]
