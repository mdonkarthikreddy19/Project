"""
Tests the edit detector on real, hand-made forgeries: the "Find it again!"
receipt forgery dataset (ICDAR 2023, L3i La Rochelle University).
https://l3i-share.univ-lr.fr/2023Finditagain/index.html

    python training/evaluate_findit.py --fetch      # pulls only the test split (~110 MB)
    python training/evaluate_findit.py              # evaluates data/external/findit2/test

The receipts are paper scans, not phone screenshots, so this is a hard
out-of-domain test of the line model, not of the UPI-specific text rules.
Writes models/findit_metrics.json.
"""
import argparse
import ast
import csv
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "external" / "findit2"
URL = "https://l3i-share.univ-lr.fr/2023Finditagain/findit2.zip"
sys.path.insert(0, str(ROOT / "backend"))


class RangeFile(io.RawIOBase):
    """Seekable view of a remote file, so zipfile can pull single members."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        self.size = int(requests.head(url, allow_redirects=True, timeout=30).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.size, self.pos + len(b)) - 1
        data = requests.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=180).content
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def fetch(split="test"):
    z = zipfile.ZipFile(RangeFile(URL))
    (OUT / split).mkdir(parents=True, exist_ok=True)
    labels = z.read(f"findit2/{split}.txt")
    (OUT / f"{split}.txt").write_bytes(labels)
    rows = list(csv.reader(io.StringIO(labels.decode("utf-8"))))
    names = [r[0] for r in rows if r and r[0].lower().endswith(".png")]

    def one(name):
        dst = OUT / split / name
        if not dst.exists():
            # each thread needs its own handle; zipfile shares file position
            zz = zipfile.ZipFile(RangeFile(URL))
            dst.write_bytes(zz.read(f"findit2/{split}/{name}"))
        return name

    with ThreadPoolExecutor(12) as ex:
        for i, _ in enumerate(ex.map(one, names), 1):
            if i % 25 == 0:
                print(f"{i}/{len(names)}", flush=True)


def edit_boxes(field):
    if not field or not field.startswith("{"):
        return []
    info = ast.literal_eval(field)
    boxes = []
    for reg in info.get("regions", []):
        if reg.get("region_attributes", {}).get("Original area") == "yes":
            continue  # copied-from source, not an edit
        s = reg["shape_attributes"]
        if s.get("name") == "rect":
            boxes.append((s["x"], s["y"], s["x"] + s["width"], s["y"] + s["height"]))
    return boxes


def overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    if a.fetch:
        fetch(a.split)

    from analysis.line_model import _load
    from analysis.line_features import line_features
    from analysis.ocr import read_lines
    bundle = _load()
    model, t = bundle["model"], bundle["threshold"]

    rows = [r for r in csv.reader(open(OUT / f"{a.split}.txt", encoding="utf-8")) if r and r[0].lower().endswith(".png")]
    ys, scores, hit_edit_line = [], [], []
    line_y, line_p = [], []
    for i, r in enumerate(rows, 1):
        path = OUT / a.split / r[0]
        if not path.exists():
            continue
        forged = r[3] == "1"
        img = Image.open(path).convert("RGB")
        lines = read_lines(img)
        if len(lines) < 3:
            continue
        rgb = np.asarray(img)
        p = model.predict_proba(line_features(rgb, [ln.box for ln in lines]))[:, 1]
        ys.append(forged)
        scores.append(float(p.max()))
        edits = edit_boxes(r[4] if len(r) > 4 else "")
        for ln, pv in zip(lines, p):
            lab = any(overlaps(ln.box, e) for e in edits)
            line_y.append(lab)
            line_p.append(float(pv))
        if forged and edits:
            top = lines[int(p.argmax())]
            hit_edit_line.append(any(overlaps(top.box, e) for e in edits))
        if i % 25 == 0:
            print(f"{i}/{len(rows)}", flush=True)

    from sklearn.metrics import roc_auc_score
    ys, scores = np.array(ys), np.array(scores)
    pred = scores >= t
    report = {
        "note": "Real hand-made forgeries on scanned paper receipts (out of domain: the model was trained on phone screenshots).",
        "images": int(len(ys)),
        "forged": int(ys.sum()),
        "image_auc": round(float(roc_auc_score(ys, scores)), 4) if 0 < ys.sum() < len(ys) else None,
        "line_auc": round(float(roc_auc_score(line_y, line_p)), 4) if 0 < sum(line_y) < len(line_y) else None,
        "forged_flagged": round(float(pred[ys].mean()), 4) if ys.any() else None,
        "authentic_flagged": round(float(pred[~ys].mean()), 4) if (~ys).any() else None,
        "top_line_is_the_edit": round(float(np.mean(hit_edit_line)), 4) if hit_edit_line else None,
    }
    (ROOT / "models" / "findit_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
