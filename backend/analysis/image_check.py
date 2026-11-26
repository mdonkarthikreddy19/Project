from __future__ import annotations

import io
import time
from datetime import timedelta

import numpy as np
from PIL import Image

from .fields import analyse_text
from .findings import Finding, combine, verdict
from .forensics import _calib, cnn_enabled, ela_image, heat_overlay, metadata, model_findings, run_model, to_data_url
from .line_model import check_lines
from .ocr import read_lines

Image.MAX_IMAGE_PIXELS = 40_000_000
FIELD_OF = {"date_invalid": "date", "time_invalid": "date", "weekday": "date", "future": "date",
            "old": "date", "vpa_handle": "vpa", "no_utr": None}
FIELD_PREFIX = {"utr_": "utr", "bank_utr": "utr", "tid_": "txn_id", "amount_": "amount", "status_": "status"}
PREVIEW_W = 720


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _preview(img: Image.Image) -> Image.Image:
    if img.width <= PREVIEW_W:
        return img
    return img.resize((PREVIEW_W, int(img.height * PREVIEW_W / img.width)), Image.LANCZOS)


def analyse_image(raw: bytes) -> dict:
    t0 = time.time()
    img = Image.open(io.BytesIO(raw))
    img.load()
    info, findings, shot_time = metadata(raw, img)
    rgb = _flatten(img)

    lines = read_lines(rgb)
    parsed = analyse_text(lines, rgb.height)
    findings += parsed.findings

    if shot_time and parsed.when and shot_time < parsed.when - timedelta(minutes=5):
        findings.append(Finding("shot_before_payment", "Screenshot was taken before the payment",
                                f"The file was created {shot_time:%d %b %Y %I:%M %p}, but the payment it shows is dated {parsed.when:%d %b %Y %I:%M %p}.",
                                2.6))

    photo = "camera" in info
    regions, heat_url = [], None
    line_check = check_lines(np.asarray(rgb), lines, parsed.boxes, photo=photo)
    if line_check:
        lf, regions, probs = line_check
        findings += lf
        info["line_model_top"] = round(float(probs.max()), 3)

    # the pixel-map CNN only votes once evaluate_model.py has shown it beats chance
    if cnn_enabled():
        model = run_model(rgb)
        if model:
            p, pm, scale = model
            mf, cnn_regions = model_findings(p, pm, scale, parsed.boxes, rgb.size, photo=photo)
            findings += mf
            regions = regions or cnn_regions
            info["model_score"] = round(p, 3)
            heat_url = to_data_url(_preview(heat_overlay(rgb, pm, _calib.get("threshold", 0.5))))

    # point at the exact field a failed check is about (the line model marks its own lines)
    flagged = []
    for f in findings:
        key = FIELD_OF.get(f.code) or next((v for k, v in FIELD_PREFIX.items() if f.code.startswith(k)), None)
        if f.kind == "bad" and key and key in parsed.boxes and key not in flagged:
            flagged.append(key)
            x0, y0, x1, y1 = parsed.boxes[key]
            regions.insert(0, {"x": max(0, x0 - 6) / rgb.width, "y": max(0, y0 - 6) / rgb.height,
                               "w": (x1 - x0 + 12) / rgb.width, "h": (y1 - y0 + 12) / rgb.height,
                               "label": f.title, "field": key})
    for r in regions:
        r.setdefault("label", "Looks edited")

    result = {
        "kind": "image",
        "flagged_fields": flagged,
        "is_receipt": parsed.is_receipt,
        "details": parsed.summary(),
        "file": info,
        "regions": regions,
        "views": {"heat": heat_url, "ela": to_data_url(_preview(ela_image(rgb)))},
        "model_loaded": line_check is not None,
    }
    if not parsed.is_receipt:
        result.update(fake_percent=None, verdict="not_receipt",
                      verdict_label="This doesn't look like a payment receipt",
                      findings=[f.to_dict() for f in findings if f.kind == "bad"])
    else:
        # with no evidence either way the answer should sit in the middle, leaning slightly genuine
        pct = combine(findings, prior=-0.3)
        key, label = verdict(pct)
        findings.sort(key=lambda f: -abs(f.weight))
        result.update(fake_percent=pct, verdict=key, verdict_label=label, findings=[f.to_dict() for f in findings])
    result["seconds"] = round(time.time() - t0, 2)
    return result
