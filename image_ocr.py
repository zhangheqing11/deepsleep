"""Local OCR for image-based user context; image bytes are never persisted."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import math
from typing import Any, Callable

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}


@dataclass(frozen=True)
class OCRResult:
    text: str
    line_count: int
    mean_confidence: float | None


@lru_cache(maxsize=1)
def _default_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "本地 OCR 依赖未安装；请运行 python -m pip install -r requirements-ocr.txt"
        ) from exc
    return RapidOCR()


def _decode_image(image_bytes: bytes):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError(
            "图片处理依赖未安装；请运行 python -m pip install -r requirements-ocr.txt"
        ) from exc

    try:
        image = Image.open(BytesIO(image_bytes))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("无法读取图片；请上传 JPEG、PNG、WebP 或 BMP 文件") from exc

    with image:
        if image.format not in SUPPORTED_FORMATS:
            raise ValueError("仅支持 JPEG、PNG、WebP 或 BMP 图片")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("暂不支持动图，请上传单帧图片")
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError(f"图片像素不能超过 {MAX_IMAGE_PIXELS:,}")
        image.load()
        rgb = image.convert("RGB")

    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "图片处理依赖未安装；请运行 python -m pip install -r requirements-ocr.txt"
        ) from exc
    # RapidOCR consumes OpenCV-style BGR arrays.
    try:
        return np.asarray(rgb)[:, :, ::-1].copy()
    finally:
        rgb.close()


def extract_image_text(
    image_bytes: bytes,
    *,
    ocr_engine: Callable[[Any], Any] | None = None,
) -> OCRResult:
    """Recognize text in an uploaded image in memory, without writing or networking."""
    if not isinstance(image_bytes, bytes):
        raise TypeError("image_bytes must be bytes")
    if not image_bytes:
        raise ValueError("image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"image size cannot exceed {MAX_IMAGE_BYTES // (1024 * 1024)} MiB")

    image = _decode_image(image_bytes)
    engine = ocr_engine if ocr_engine is not None else _default_ocr_engine()
    result = engine(image)
    detections = result[0] if isinstance(result, tuple) else result
    if detections is None:
        return OCRResult(text="", line_count=0, mean_confidence=None)
    if not isinstance(detections, (list, tuple)):
        raise RuntimeError("OCR engine returned an unsupported result")

    lines = []
    confidences = []
    for detection in detections:
        if not isinstance(detection, (list, tuple)) or len(detection) < 3:
            raise RuntimeError("OCR engine returned a malformed text line")
        text = detection[1]
        if not isinstance(text, str):
            raise RuntimeError("OCR engine returned non-text content")
        text = text.strip()
        if not text:
            continue
        lines.append(text)
        try:
            confidence = float(detection[2])
        except (TypeError, ValueError):
            continue
        if math.isfinite(confidence) and 0 <= confidence <= 1:
            confidences.append(confidence)

    return OCRResult(
        text="\n".join(lines),
        line_count=len(lines),
        mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
    )
