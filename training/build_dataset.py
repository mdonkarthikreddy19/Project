"""
Writes the synthetic training set to data/synth/<split>/.

    python training/build_dataset.py --train 2500 --val 300 --test 400

Each split gets images/, masks/ (fakes only) and labels.csv.
Seeds don't overlap between splits, so the test set is never seen in training.
"""
import argparse
import csv
import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from receipt_synth import make_sample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent / "data" / "synth"
SEED_BASE = {"train": 1_000_000, "val": 2_000_000, "test": 3_000_000}


def work(args):
    split, idx = args
    fake = idx % 2 == 1
    seed = SEED_BASE[split] + idx
    img, mask, fmt, meta, raw = make_sample(seed, fake)
    name = f"{split}_{idx:05d}"
    out = ROOT / split
    # write the exact bytes the share pipeline produced - re-saving would add another compression round
    (out / "images" / f"{name}.{fmt}").write_bytes(raw)
    if mask is not None:
        mask.point(lambda p: 255 if p > 127 else 0).save(out / "masks" / f"{name}.png")
    meta["file"] = f"{name}.{fmt}"
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=5000)
    ap.add_argument("--val", type=int, default=600)
    ap.add_argument("--test", type=int, default=800)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    for split, n in (("train", a.train), ("val", a.val), ("test", a.test)):
        (ROOT / split / "images").mkdir(parents=True, exist_ok=True)
        (ROOT / split / "masks").mkdir(parents=True, exist_ok=True)
        with Pool(a.workers) as pool:
            rows = pool.map(work, [(split, i) for i in range(n)], chunksize=16)
        with open(ROOT / split / "labels.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(split, n, "done", json.dumps({"fake": sum(r["fake"] for r in rows)}))


if __name__ == "__main__":
    main()
