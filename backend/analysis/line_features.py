"""
Per-text-line forensic features.

Edited text almost never matches the untouched lines around it, so every
feature is either measured against the line's own surroundings (the ring of
background just outside its box) or against the other lines of the same
screenshot:

  background   fill colour and noise inside the box vs. the ring outside it
  seams        straight edges just outside the text, left by an erase rectangle
  compression  error level (ELA) and 8x8 JPEG blockiness vs. other lines
  ink          text colour, anti-aliasing and stroke contrast vs. other lines
  alignment    how far the ink edge sits from the nearest other line's edge

Used for training (training/train_line_model.py) and at request time with
OCR boxes, so it must only depend on pixels + a box.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

FEATURE_NAMES = [
    "bg_shift", "bg_noise_ratio", "ring_noise", "seam_v", "seam_h",
    "ela_text", "ela_bg", "ela_ring", "block_in", "block_ring",
    "aa_ratio", "ink_contrast", "height", "width_rel", "y_rel",
    "ela_text_z", "aa_z", "contrast_z", "color_nearest", "align_dist",
    "noise_z", "block_z", "bg_shift_z", "n_lines", "global_ela", "global_noise",
]


def _ela(rgb: np.ndarray) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=90)
    buf.seek(0)
    re = np.asarray(Image.open(buf).convert("RGB")).astype(np.int16)
    return np.abs(rgb.astype(np.int16) - re).max(axis=2).astype(np.float32)


def _blockiness(g: np.ndarray) -> float:
    """Ratio of luminance jumps on the 8-px JPEG grid vs. off it (1.0 = no grid)."""
    if g.shape[1] < 18 or g.shape[0] < 4:
        return 1.0
    d = np.abs(np.diff(g, axis=1))
    cols = np.arange(d.shape[1])
    on = d[:, (cols % 8) == 7].mean()
    off = d[:, (cols % 8) != 7].mean()
    return float((on + 0.05) / (off + 0.05))


def _seam(gx: np.ndarray, rows: slice, cols: list[int]) -> float:
    """Strongest straight vertical edge among candidate columns, vs. their median."""
    vals = [gx[rows, c].mean() for c in cols if 0 <= c < gx.shape[1]]
    if len(vals) < 3:
        return 0.0
    vals = np.array(vals)
    return float(vals.max() - np.median(vals))


def _robust_z(v: np.ndarray, peers: np.ndarray) -> np.ndarray:
    med = np.median(peers)
    mad = np.median(np.abs(peers - med)) + 1e-3
    return (v - med) / (1.4826 * mad)


def line_features(rgb: np.ndarray, boxes: list[tuple]) -> np.ndarray:
    """rgb: HxWx3 uint8. boxes: (x0, y0, x1, y1) per text line. Returns (n, len(FEATURE_NAMES))."""
    H, W = rgb.shape[:2]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    noise = np.abs(g - cv2.medianBlur(g.astype(np.uint8), 3).astype(np.float32))
    gx = np.abs(np.diff(g, axis=1, append=g[:, -1:]))
    gy = np.abs(np.diff(g, axis=0, append=g[-1:, :]))
    ela = _ela(rgb)
    rgbf = rgb.astype(np.float32)

    raw = []
    for (x0, y0, x1, y1) in boxes:
        x0, y0 = int(max(0, np.floor(x0)) ), int(max(0, np.floor(y0)))
        x1, y1 = int(min(W, np.ceil(x1))), int(min(H, np.ceil(y1)))
        h = max(1, y1 - y0)
        p = max(3, int(h * 0.25))
        bx0, by0, bx1, by1 = max(0, x0 - 2), max(0, y0 - 2), min(W, x1 + 2), min(H, y1 + 2)
        rx0, ry0, rx1, ry1 = max(0, x0 - p - 6), max(0, y0 - p - 6), min(W, x1 + p + 6), min(H, y1 + p + 6)
        ring_mask = np.ones((ry1 - ry0, rx1 - rx0), bool)
        ring_mask[max(0, y0 - p) - ry0:min(H, y1 + p) - ry0, max(0, x0 - p) - rx0:min(W, x1 + p) - rx0] = False
        if bx1 - bx0 < 3 or by1 - by0 < 3 or not ring_mask.any():
            raw.append(None)
            continue

        ring_rgb = rgbf[ry0:ry1, rx0:rx1][ring_mask]
        bg = np.median(ring_rgb, axis=0)
        box_rgb = rgbf[by0:by1, bx0:bx1]
        dist = np.abs(box_rgb - bg).sum(axis=2)
        dmax = max(dist.max(), 1.0)
        is_bg = dist < max(12.0, 0.08 * dmax)
        is_text = dist > 0.5 * dmax
        is_edge = (dist > 0.1 * dmax) & ~is_text

        box_noise = noise[by0:by1, bx0:bx1]
        ring_noise = noise[ry0:ry1, rx0:rx1][ring_mask]
        bg_in = box_rgb[is_bg].mean(axis=0) if is_bg.any() else bg
        box_ela = ela[by0:by1, bx0:bx1]
        rows = slice(y0, max(y0 + 1, y1))
        cols_l = list(range(x0 - p - 4, x0))
        cols_r = list(range(x1, x1 + p + 4))
        seam_v = max(_seam(gx, rows, cols_l), _seam(gx, rows, cols_r))
        gyt = gy.T
        cols = slice(x0, max(x0 + 1, x1))
        seam_h = max(_seam(gyt, cols, list(range(y0 - p - 4, y0))), _seam(gyt, cols, list(range(y1, y1 + p + 4))))
        ink_cols = np.nonzero(is_text.any(axis=0))[0]
        ink_l = bx0 + (ink_cols[0] if len(ink_cols) else 0)
        ink_r = bx0 + (ink_cols[-1] if len(ink_cols) else bx1 - bx0)
        text_color = box_rgb[is_text].mean(axis=0) if is_text.any() else bg

        raw.append(dict(
            bg_shift=float(np.abs(bg_in - bg).sum()),
            bg_noise=float(box_noise[is_bg].mean()) if is_bg.any() else 0.0,
            ring_noise=float(ring_noise.mean()),
            seam_v=seam_v, seam_h=seam_h,
            ela_text=float(box_ela[is_text].mean()) if is_text.any() else 0.0,
            ela_bg=float(box_ela[is_bg].mean()) if is_bg.any() else 0.0,
            ela_ring=float(ela[ry0:ry1, rx0:rx1][ring_mask].mean()),
            block_in=_blockiness(g[by0:by1, bx0:bx1]),
            block_ring=_blockiness(g[ry0:ry1, rx0:rx1]),
            aa=float(is_edge.sum() / max(1, is_text.sum() + is_edge.sum())),
            contrast=float(dmax),
            h=float(h), w=float(x1 - x0), y=float(y0),
            ink_l=float(ink_l), ink_r=float(ink_r), ink_c=float((ink_l + ink_r) / 2),
            color=text_color,
        ))

    ok = [r for r in raw if r is not None]
    n = len(boxes)
    feats = np.zeros((n, len(FEATURE_NAMES)), np.float32)
    if not ok:
        return feats
    arr = lambda k: np.array([r[k] for r in ok], np.float32)  # noqa: E731
    ela_t, aa, con, noi, blk, bgs = arr("ela_text"), arr("aa"), arr("contrast"), arr("bg_noise"), arr("block_in"), arr("bg_shift")
    heights = arr("h")
    g_ela = float(np.median(ela))
    g_noise = float(noise.mean())

    j = 0
    for i, r in enumerate(raw):
        if r is None:
            continue
        # compare with lines of a similar size; fall back to all lines
        same = np.abs(heights - r["h"]) <= 0.35 * r["h"]
        peers = same if same.sum() >= 3 else np.ones_like(same)
        others = [o for o in ok if o is not r]
        color_nearest = min((float(np.abs(o["color"] - r["color"]).sum()) for o in others), default=0.0)
        align = min((min(abs(o["ink_l"] - r["ink_l"]), abs(o["ink_r"] - r["ink_r"]), abs(o["ink_c"] - r["ink_c"]))
                     for o in others), default=20.0)
        feats[i] = [
            r["bg_shift"],
            np.log((r["bg_noise"] + 0.05) / (r["ring_noise"] + 0.05)),
            r["ring_noise"],
            r["seam_v"], r["seam_h"],
            r["ela_text"], r["ela_bg"], r["ela_ring"],
            r["block_in"], r["block_ring"],
            r["aa"], r["contrast"],
            r["h"], r["w"] / W, r["y"] / H,
            _robust_z(np.float32(r["ela_text"]), ela_t[peers]),
            _robust_z(np.float32(r["aa"]), aa[peers]),
            _robust_z(np.float32(r["contrast"]), con[peers]),
            min(color_nearest, 200.0),
            min(align, 20.0),
            _robust_z(np.float32(r["bg_noise"]), noi),
            _robust_z(np.float32(r["block_in"]), blk),
            _robust_z(np.float32(r["bg_shift"]), bgs),
            float(len(ok)), g_ela, g_noise,
        ]
        j += 1
    return np.nan_to_num(np.clip(feats, -50, 1e4))
