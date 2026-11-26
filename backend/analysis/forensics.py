"""
Pixel- and file-level checks:

* metadata left behind by editing apps (EXIF Software, XMP history, PNG text chunks)
* a screenshot timestamp earlier than the payment it claims to show
* the trained TamperNet heat map, mapped back onto the fields OCR found
* an error-level (ELA) view for people who want to look for themselves
"""
from __future__ import annotations

import base64
import io
import re
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image, ImageChops, ImageFilter

from .findings import Finding

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "tamper_net.pt"
CALIB_PATH = MODEL_PATH.with_name("calibration.json")

EDITORS = ["photoshop", "gimp", "picsart", "snapseed", "canva", "lightroom", "pixlr", "photodirector",
           "pixellab", "polarr", "meitu", "fotor", "affinity", "paint.net", "photopea", "inshot",
           "remini", "facetune", "vsco", "photoroom", "picmonkey", "befunky", "krita", "ps express",
           "photo editor", "phonto", "text on photo"]

_net = None
_net_lock = threading.Lock()
_calib = {"threshold": 0.5}


# ------------------------------------------------------------------ metadata

def metadata(raw: bytes, img: Image.Image) -> tuple[dict, list[Finding], datetime | None]:
    info: dict = {"format": img.format, "width": img.width, "height": img.height}
    findings: list[Finding] = []
    shot_time = None

    exif = {}
    try:
        for k, v in (img.getexif() or {}).items():
            exif[ExifTags.TAGS.get(k, str(k))] = v
        sub = img.getexif().get_ifd(0x8769)
        for k, v in sub.items():
            exif[ExifTags.TAGS.get(k, str(k))] = v
    except Exception:
        pass

    software = str(exif.get("Software", "") or "")
    texts = [software]
    if img.format == "PNG":
        for k, v in (img.info or {}).items():
            if isinstance(v, str):
                texts.append(f"{k}={v}")
                if k.lower() == "software":
                    software = software or v
    head = raw[:300_000].decode("latin-1", errors="ignore")
    xmp = re.search(r"<x:xmpmeta.*?</x:xmpmeta>", head, re.S)
    if xmp:
        texts.append(xmp.group(0))
    if software:
        info["software"] = software
    if exif.get("Make") or exif.get("Model"):
        info["camera"] = f"{exif.get('Make', '')} {exif.get('Model', '')}".strip()

    blob = " ".join(texts).lower()
    hit = next((e for e in EDITORS if e in blob), None)
    if hit:
        findings.append(Finding("editor_meta", "Saved by a photo editor",
                                f"The file's metadata names an editing app ({hit.title()}). A screenshot sent straight from a payment app wouldn't carry this.",
                                2.4))
    elif xmp and ("xmpmm:history" in blob or "stevt:action" in blob):
        findings.append(Finding("edit_history", "File has an edit history",
                                "The XMP metadata records save/edit actions, which payment apps don't write.", 1.6))

    if "camera" in info and not hit:
        findings.append(Finding("photo", "This is a camera photo, not a screenshot",
                                f"Taken with {info['camera']}. Photos of a screen hide editing traces, so the image checks are less reliable.", 0.3))

    for key in ("DateTimeOriginal", "DateTime"):
        v = exif.get(key)
        if v:
            try:
                shot_time = datetime.strptime(str(v).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
                info["file_time"] = shot_time.strftime("%d %b %Y, %I:%M %p")
                break
            except ValueError:
                pass

    if img.format == "JPEG":
        q = estimate_jpeg_quality(img)
        if q:
            info["jpeg_quality"] = q
    return info, findings, shot_time


def estimate_jpeg_quality(img: Image.Image) -> int | None:
    """Rough IJG quality from the luminance quantisation table."""
    try:
        qt = img.quantization[0]
    except Exception:
        return None
    std = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
           14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
           49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
    ratio = np.mean([q / s for q, s in zip(list(qt)[:64], std)]) * 100
    quality = (200 - ratio) / 2 if ratio <= 100 else 5000 / ratio
    return int(np.clip(round(quality), 1, 100))


# ------------------------------------------------------------------ images for the UI

def to_data_url(img: Image.Image, fmt="JPEG", quality=85) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality)
    else:
        img.save(buf, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def ela_image(img: Image.Image, quality=90) -> Image.Image:
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    diff = ImageChops.difference(rgb, Image.open(buf).convert("RGB"))
    arr = np.asarray(diff).astype(np.float32).max(axis=2)
    scale = 255 / max(8.0, np.percentile(arr, 99.7))
    arr = np.clip(arr * scale, 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("RGB")


def heat_overlay(img: Image.Image, prob: np.ndarray, threshold: float) -> Image.Image:
    base = img.convert("RGB")
    heat = Image.fromarray((np.clip(prob, 0, 1) * 255).astype(np.uint8)).resize(base.size, Image.BILINEAR)
    heat = heat.filter(ImageFilter.GaussianBlur(radius=max(2, base.width // 200)))
    h = np.asarray(heat).astype(np.float32) / 255
    alpha = np.clip((h - threshold * 0.6) / max(1e-3, 1 - threshold * 0.6), 0, 1)[..., None] * 0.6
    gray = np.asarray(base.convert("L").convert("RGB")).astype(np.float32)
    dim = gray * 0.75 + 64
    red = np.array([226, 54, 54], np.float32)
    out = dim * (1 - alpha) + red * alpha
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


# ------------------------------------------------------------------ the learned model

def _load_net():
    global _net
    if _net is not None or not MODEL_PATH.exists():
        return _net
    with _net_lock:
        if _net is None:
            import json
            import torch

            from .tamper_net import TamperNet
            net = TamperNet()
            net.load_state_dict(torch.load(MODEL_PATH, map_location="cpu", weights_only=True))
            net.eval()
            if CALIB_PATH.exists():
                _calib.update(json.loads(CALIB_PATH.read_text()))
            _net = net
    return _net


def model_available() -> bool:
    return _load_net() is not None


def cnn_enabled() -> bool:
    """calibration.json carries "use": true only when the CNN beat chance on the held-out set."""
    if not MODEL_PATH.exists() or not CALIB_PATH.exists():
        return False
    import json
    return bool(json.loads(CALIB_PATH.read_text()).get("use", False))


def run_model(img: Image.Image, max_side=2400):
    """Returns (image probability, probability map at 1/8 scale, scale used) or None if no model."""
    net = _load_net()
    if net is None:
        return None
    import torch

    from .tamper_net import image_logit
    work = img.convert("RGB")
    scale = 1.0
    if max(work.size) > max_side:
        scale = max_side / max(work.size)
        work = work.resize((int(work.width * scale), int(work.height * scale)), Image.BICUBIC)
    x = torch.from_numpy(np.asarray(work).copy()).permute(2, 0, 1).float()[None] / 255
    with torch.inference_mode():
        lm = net(x)
        p = torch.sigmoid(image_logit(lm)).item()
        pm = torch.sigmoid(lm)[0, 0].numpy()
    return p, pm, scale


def label_regions(hot: np.ndarray, pm: np.ndarray):
    """Bounding boxes of 8-connected hot cells, strongest first. The grid is small, so plain BFS is fine."""
    seen = np.zeros_like(hot, dtype=bool)
    H, W = hot.shape
    out = []
    for sy, sx in zip(*np.nonzero(hot)):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        r0 = r1 = sy
        c0 = c1 = sx
        best = 0.0
        while stack:
            y, x = stack.pop()
            r0, r1, c0, c1 = min(r0, y), max(r1, y), min(c0, x), max(c1, x)
            best = max(best, float(pm[y, x]))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and hot[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        out.append((r0, c0, r1, c1, best))
    out.sort(key=lambda r: -r[4])
    return out


def model_findings(p: float, pm: np.ndarray, scale: float, field_boxes: dict, img_size,
                   photo: bool = False) -> tuple[list[Finding], list[dict]]:
    t = _calib.get("threshold", 0.5)
    findings = []
    regions = []
    stride = 8 / scale
    hot = pm >= max(t, 0.35)
    names = {"amount": "amount", "utr": "UTR / reference number", "date": "date and time", "payee": "payee name",
             "vpa": "UPI ID", "txn_id": "transaction ID", "status": "status line"}
    touched = []
    if hot.any():
        for key, (x0, y0, x1, y1) in field_boxes.items():
            gx0, gy0 = int(x0 / stride), int(y0 / stride)
            gx1, gy1 = int(np.ceil(x1 / stride)), int(np.ceil(y1 / stride))
            cell = pm[max(0, gy0 - 1):gy1 + 1, max(0, gx0 - 1):gx1 + 1]
            if cell.size and cell.max() >= max(t, 0.35):
                touched.append((float(cell.max()), key))
        # boxes for the UI: connected hot cells, coarse
        for (r0, c0, r1, c1, score) in label_regions(hot, pm)[:6]:
            regions.append({"x": c0 * stride / img_size[0], "y": r0 * stride / img_size[1],
                            "w": (c1 - c0 + 1) * stride / img_size[0], "h": (r1 - r0 + 1) * stride / img_size[1],
                            "score": round(score, 3)})
    touched.sort(reverse=True)

    # map the probability onto evidence weight; centred on the calibrated threshold
    logit = float(np.log(max(p, 1e-4) / max(1 - p, 1e-4)) - np.log(t / (1 - t)))
    w = float(np.clip(logit * 0.9, -1.6, 3.2))
    if photo:
        # the model learned from screenshots; camera noise and paper texture throw it off
        w *= 0.35
    if p >= t:
        where = ", ".join(names.get(k, k) for _, k in touched[:3])
        detail = (f"The pixels around the {where} don't match the rest of the screenshot - different compression noise or text edges. "
                  "This is what retyped or pasted text looks like." if where else
                  "Some regions have noise and edge patterns that don't match the rest of the screenshot. See the highlighted areas.")
        if photo:
            detail += " This is a camera photo, so treat this result loosely."
        findings.append(Finding("model_edit", "Signs of editing in the image", detail, w))
    else:
        findings.append(Finding("model_clean", "No signs of pixel editing",
                                "The text and background have consistent compression noise and edges throughout.", w))
    return findings, regions
