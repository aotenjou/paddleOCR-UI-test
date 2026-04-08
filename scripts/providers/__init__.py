"""Provider abstractions for PaddleOCR UI test."""

from .ocr import (
    OCR_PROVIDER_REGISTRY,
    PaddleOCRProvider,
    create_ocr_provider,
    describe_ocr_provider,
    list_ocr_providers,
)

__all__ = [
    "OCR_PROVIDER_REGISTRY",
    "PaddleOCRProvider",
    "create_ocr_provider",
    "describe_ocr_provider",
    "list_ocr_providers",
]
