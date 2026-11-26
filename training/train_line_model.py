"""
Trains the per-line edit detector (gradient-boosted trees on line_features).

    python training/train_line_model.py

Line boxes come from re-rendering each synthetic receipt from its seed (the
renderer is deterministic), scaled to the saved image and jittered a little
so they look like OCR boxes. A line is "edited" when the tamper mask covers
part of it. Image score = the most suspicious line.

Real screenshots in data/real/ are added automatically (boxes from OCR, the
same way the website sees them) and weighted higher than synthetic ones:
    data/real/genuine/*.jpg|png
    data/real/fake/*.jpg|png  +  data/real/fake_masks/<same name>.png (white = edited)
Every 5th real image is held out and reported separately as the real-world score.

Writes models/line_model.joblib and models/line_model_metrics.json.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "training"))
sys.path.insert(0, str(ROOT / "backend"))
from analysis.line_features import FEATURE_NAMES, line_features  # noqa: E402
from receipt_synth import render  # noqa: E402

SYNTH = ROOT / "data" / "synth"
REAL = ROOT / "data" / "real"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
REAL_WEIGHT = 5.0


def boxes_for(seed: int, size) -> list:
    rng = random.Random(seed)
    rec = render(rng)  # make_sample() renders first, so the layout matches the saved image
    sx, sy = size[0] / rec.image.width, size[1] / rec.image.height
    jit = random.Random(seed + 7)
    out = []
    for it in rec.items:
        x0, y0, x1, y1 = it.bbox
        out.append((x0 * sx + jit.uniform(-3, 2), y0 * sy + jit.uniform(-3, 2),
                    x1 * sx + jit.uniform(-2, 3), y1 * sy + jit.uniform(-2, 3)))
    return out


def work(args):
    split, row = args
    img_path = SYNTH / split / "images" / row["file"]
    rgb = np.asarray(Image.open(img_path).convert("RGB"))
    H, W = rgb.shape[:2]
    boxes = boxes_for(int(row["seed"]), (W, H))
    feats = line_features(rgb, boxes)
    labels = np.zeros(len(boxes), np.int8)
    if row["fake"] == "True":
        m = np.asarray(Image.open(SYNTH / split / "masks" / (Path(row["file"]).stem + ".png"))) > 127
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            x0, y0 = max(0, int(x0)), max(0, int(y0))
            x1, y1 = min(W, int(x1) + 1), min(H, int(y1) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            covered = m[y0:y1, x0:x1]
            # a single changed digit only covers a sliver of a long line, so count glyph-sized edits too
            if covered.mean() > 0.15 or covered.sum() >= 0.25 * (y1 - y0) ** 2:
                labels[i] = 1
    kind = row["tamper"].split("+")[0].split(":")[0]
    return feats, labels, row["fake"] == "True", kind, Path(row["file"]).suffix


def load(split, workers=5):
    rows = list(csv.DictReader(open(SYNTH / split / "labels.csv", encoding="utf-8")))
    with Pool(workers) as pool:
        res = pool.map(work, [(split, r) for r in rows], chunksize=8)
    return res


def real_work(args):
    path, mask_path = args
    from analysis.ocr import read_lines
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img)
    H, W = rgb.shape[:2]
    # same boxes the website uses: OCR lines below the phone's status bar
    boxes = [ln.box for ln in read_lines(img) if ln.box[3] > H * 0.045]
    feats = line_features(rgb, boxes) if boxes else np.zeros((0, len(FEATURE_NAMES)), np.float32)
    labels = np.zeros(len(boxes), np.int8)
    if mask_path is not None:
        m = Image.open(mask_path).convert("L")
        m = np.asarray(m.resize((W, H)) if m.size != (W, H) else m) > 127
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(W, int(x1) + 1), min(H, int(y1) + 1)
            covered = m[y0:y1, x0:x1]
            if covered.size and (covered.mean() > 0.15 or covered.sum() >= 0.25 * (y1 - y0) ** 2):
                labels[i] = 1
    return feats, labels, mask_path is not None, "real", path.suffix


def load_real(workers=2):
    items = []
    for p in sorted((REAL / "genuine").glob("*")) if (REAL / "genuine").exists() else []:
        if p.suffix.lower() in IMAGE_EXT:
            items.append((p, None))
    skipped = 0
    for p in sorted((REAL / "fake").glob("*")) if (REAL / "fake").exists() else []:
        if p.suffix.lower() not in IMAGE_EXT:
            continue
        m = REAL / "fake_masks" / (p.stem + ".png")
        if m.exists():
            items.append((p, m))
        else:
            skipped += 1
    if skipped:
        print(f"skipped {skipped} real fakes without a mask in data/real/fake_masks/", flush=True)
    if not items:
        return [], []
    with Pool(workers) as pool:
        res = pool.map(real_work, items)
    train = [r for i, r in enumerate(res) if i % 5 != 0]
    held = [r for i, r in enumerate(res) if i % 5 == 0]
    return train, held


def flatten(res):
    X = np.concatenate([r[0] for r in res])
    y = np.concatenate([r[1] for r in res])
    img = np.concatenate([np.full(len(r[1]), i) for i, r in enumerate(res)])
    return X, y, img


def image_scores(model, res):
    scores = []
    for feats, *_ in res:
        p = model.predict_proba(feats)[:, 1] if len(feats) else np.array([0.0])
        scores.append(float(p.max()))
    return np.array(scores)


def main():
    print("building line features...", flush=True)
    tr, va, te = load("train"), load("val"), load("test")
    real_tr, real_te = load_real()
    Xtr, ytr, _ = flatten(tr + real_tr)
    weight = np.ones(len(ytr))
    n_real_lines = sum(len(r[1]) for r in real_tr)
    if n_real_lines:
        weight[-n_real_lines:] = REAL_WEIGHT
    print(f"train lines {len(ytr)} edited {int(ytr.sum())} (real images {len(real_tr)}, held out {len(real_te)})", flush=True)
    model = HistGradientBoostingClassifier(max_iter=500, learning_rate=0.05, max_leaf_nodes=31,
                                           l2_regularization=1.0, class_weight="balanced", random_state=0)
    model.fit(Xtr, ytr, sample_weight=weight)

    Xva, yva, _ = flatten(va)
    sva = image_scores(model, va)
    yva_img = np.array([r[2] for r in va])
    best_t, best = 0.5, -1
    for t in np.linspace(0.05, 0.95, 181):
        s = 0.45 * (sva[yva_img] >= t).mean() + 0.55 * (sva[~yva_img] < t).mean()
        if s > best:
            best_t, best = float(t), s

    Xte, yte, _ = flatten(te)
    ste = image_scores(model, te)
    yte_img = np.array([r[2] for r in te])
    pred = ste >= best_t
    by_kind, by_fmt = defaultdict(list), defaultdict(list)
    for r, p_ok in zip(te, pred == yte_img):
        if r[2]:
            by_kind[r[3]].append(p_ok)
        by_fmt[r[4] + ("_fake" if r[2] else "_genuine")].append(p_ok)
    rate = lambda d: {k: round(float(np.mean(v)), 3) for k, v in sorted(d.items())}  # noqa: E731
    metrics = {
        "note": "Synthetic test split rendered from unseen seeds. Real-world accuracy is not measured by this.",
        "threshold": round(best_t, 3),
        "line_auc_val": round(roc_auc_score(yva, model.predict_proba(Xva)[:, 1]), 4),
        "line_auc_test": round(roc_auc_score(yte, model.predict_proba(Xte)[:, 1]), 4),
        "image_auc_val": round(roc_auc_score(yva_img, sva), 4),
        "image_auc_test": round(roc_auc_score(yte_img, ste), 4),
        "test_accuracy": round(float((pred == yte_img).mean()), 4),
        "fakes_caught": round(float(pred[yte_img].mean()), 4),
        "genuine_false_alarms": round(float(pred[~yte_img].mean()), 4),
        "detection_by_edit_type": rate(by_kind),
        "accuracy_by_format": rate(by_fmt),
        "features": FEATURE_NAMES,
        "real_images_trained": len(real_tr),
    }
    if real_te:
        sr = image_scores(model, real_te)
        yr = np.array([r[2] for r in real_te])
        pr = sr >= best_t
        metrics["real_holdout"] = {
            "images": len(real_te),
            "accuracy": round(float((pr == yr).mean()), 4),
            "fakes_caught": round(float(pr[yr].mean()), 4) if yr.any() else None,
            "genuine_false_alarms": round(float(pr[~yr].mean()), 4) if (~yr).any() else None,
            "image_auc": round(roc_auc_score(yr, sr), 4) if 0 < yr.sum() < len(yr) else None,
        }
    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump({"model": model, "threshold": best_t, "features": FEATURE_NAMES}, ROOT / "models" / "line_model.joblib")
    (ROOT / "models" / "line_model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
