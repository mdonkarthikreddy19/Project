"""Runs the trained per-line edit detector on OCR line boxes."""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from .findings import Finding
from .line_features import line_features
from .ocr import Line

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "line_model.joblib"
_bundle = None
# real screenshots are noisier than the synthetic validation set; only trust strong hits
STRICT_THRESHOLD = 0.95
_lock = threading.Lock()

FIELD_NAMES = {"amount": "amount", "utr": "UTR / reference number", "date": "date and time", "payee": "payee name",
               "vpa": "UPI ID", "txn_id": "transaction ID", "status": "status line"}


def _load():
    global _bundle
    if _bundle is None and MODEL_PATH.exists():
        with _lock:
            if _bundle is None:
                import joblib
                _bundle = joblib.load(MODEL_PATH)
    return _bundle


def available() -> bool:
    return _load() is not None


def _overlaps(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def check_lines(rgb: np.ndarray, lines: list[Line], field_boxes: dict, photo: bool = False):
    """Returns (findings, regions, per-line probabilities) or None when the model isn't trained yet."""
    bundle = _load()
    if bundle is None or len(lines) < 3:
        return None
    H, W = rgb.shape[:2]
    # skip the phone's status bar: clock and icons are drawn differently from app text
    # logos and icon text ("UPI", "KR") are drawn, not typeset, and look nothing like body text
    use = [ln for ln in lines if ln.box[3] > H * 0.045 and sum(ch.isalnum() for ch in ln.text) >= 4]
    if len(use) < 3:
        return None
    all_probs = bundle["model"].predict_proba(line_features(rgb, [ln.box for ln in use]))[:, 1]
    # Forgers edit the facts: amount, UTR, date, IDs, names. Avatars, logos, emoji, ads and
    # buttons on real screenshots look "odd" to the model but prove nothing, so only fact
    # lines get a vote.
    keyed = [(p, ln) for p, ln in zip(all_probs, use)
             if any(_overlaps(ln.box, b) for k, b in field_boxes.items() if k in FIELD_NAMES and k != "status")]
    if not keyed:
        return None
    probs = np.array([p for p, _ in keyed])
    use = [ln for _, ln in keyed]
    t = max(bundle["threshold"], STRICT_THRESHOLD)
    top = float(probs.max())

    regions = []
    flagged = sorted(((p, ln) for p, ln in zip(probs, use) if p >= t), key=lambda x: -x[0])
    for p, ln in flagged[:5]:
        x0, y0, x1, y1 = ln.box
        regions.append({"x": max(0, x0 - 4) / W, "y": max(0, y0 - 4) / H,
                        "w": (x1 - x0 + 8) / W, "h": (y1 - y0 + 8) / H, "score": round(float(p), 3)})

    # evidence weight, centred on the calibrated threshold
    logit = np.log(max(top, 1e-4) / max(1 - top, 1e-4)) - np.log(t / (1 - t))
    # crossing the threshold is strong evidence on its own; a clean result only nudges toward genuine
    w = float(np.clip(0.9 + logit * 1.2, 0.9, 3.2)) if top >= t else float(np.clip(logit * 0.5, -0.8, 0.0))
    if photo:
        # trained on screenshots; camera noise and paper texture confuse it, so it only leaves a note
        w = float(np.clip(w * 0.35, -0.3, 0.3))

    if top >= t:
        fields = []
        for _, ln in flagged:
            for key, box in field_boxes.items():
                if _overlaps(ln.box, box) and FIELD_NAMES.get(key) and FIELD_NAMES[key] not in fields:
                    fields.append(FIELD_NAMES[key])
        quoted = ", ".join(f"“{ln.text}”" for _, ln in flagged[:2])
        where = f"the {' and '.join(fields[:2])}" if fields else quoted
        detail = (f"The text of {where} doesn't match the rest of the screenshot: its background, compression noise "
                  "or letter edges differ from the lines around it. That's what retyped or pasted-in text looks like.")
        if photo:
            detail += " This is a camera photo, so treat this result loosely."
        return [Finding("lines_edited", "A line of text looks edited", detail, w)], regions, probs
    return [Finding("lines_clean", "Text looks untouched",
                    "Every line of text has the same background, compression noise and letter edges as its neighbours.", w)], [], probs
