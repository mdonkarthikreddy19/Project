"""Thin wrapper around RapidOCR (ONNX, runs on CPU, no Tesseract install needed)."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image

_engine = None
_lock = threading.Lock()


@dataclass
class Line:
    text: str
    box: tuple  # x0, y0, x1, y1 in original image pixels
    conf: float

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    @property
    def squashed(self) -> str:
        return "".join(self.text.split()).lower()


def _get():
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR()
    return _engine


def read_lines(img: Image.Image, max_side: int = 1700) -> list[Line]:
    scale = 1.0
    work = img.convert("RGB")
    if max(work.size) > max_side:
        scale = max_side / max(work.size)
        work = work.resize((int(work.width * scale), int(work.height * scale)), Image.LANCZOS)
    arr = np.asarray(work)[:, :, ::-1].copy()  # RapidOCR expects BGR like cv2
    result, _ = _get()(arr)
    lines = []
    for quad, text, conf in result or []:
        xs = [p[0] / scale for p in quad]
        ys = [p[1] / scale for p in quad]
        lines.append(Line(text.strip(), (min(xs), min(ys), max(xs), max(ys)), float(conf)))
    lines.sort(key=lambda l: (round(l.box[1] / 12), l.box[0]))
    return lines
