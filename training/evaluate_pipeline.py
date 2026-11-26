"""
End-to-end check of what the website actually returns: OCR + text rules +
metadata + line model, scored exactly like /api/check/image.

    python training/evaluate_pipeline.py --n 200

Writes models/pipeline_metrics.json.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from analysis.image_check import analyse_image  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    d = ROOT / "data" / "synth" / "test"
    rows = list(csv.DictReader(open(d / "labels.csv", encoding="utf-8")))[: a.n]
    verdicts = {"genuine": Counter(), "fake": Counter()}
    by_kind = defaultdict(list)
    pcts = {"genuine": [], "fake": []}
    for i, r in enumerate(rows):
        res = analyse_image((d / "images" / r["file"]).read_bytes())
        kind = "fake" if r["fake"] == "True" else "genuine"
        verdicts[kind][res["verdict"]] += 1
        if res["fake_percent"] is not None:
            pcts[kind].append(res["fake_percent"])
        if kind == "fake":
            by_kind[r["tamper"].split("+")[0].split(":")[0]].append(res["verdict"] == "fake")
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{len(rows)}", flush=True)
    g, f = sum(verdicts["genuine"].values()), sum(verdicts["fake"].values())
    report = {
        "note": "Full website pipeline on the synthetic test split. Real-world accuracy is not measured by this.",
        "images": len(rows),
        "genuine_verdicts": {k: round(v / g, 3) for k, v in verdicts["genuine"].items()},
        "fake_verdicts": {k: round(v / f, 3) for k, v in verdicts["fake"].items()},
        "fakes_called_fake": round(verdicts["fake"]["fake"] / f, 3),
        "fakes_called_fake_or_unsure": round((verdicts["fake"]["fake"] + verdicts["fake"]["unsure"]) / f, 3),
        "genuine_called_fake": round(verdicts["genuine"]["fake"] / g, 3),
        "genuine_called_genuine": round(verdicts["genuine"]["genuine"] / g, 3),
        "median_percent_genuine": float(np.median(pcts["genuine"])) if pcts["genuine"] else None,
        "median_percent_fake": float(np.median(pcts["fake"])) if pcts["fake"] else None,
        "fake_verdict_rate_by_edit_type": {k: round(float(np.mean(v)), 3) for k, v in sorted(by_kind.items())},
    }
    (ROOT / "models" / "pipeline_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
