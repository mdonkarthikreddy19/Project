"""
Measures the OCR + consistency checks on the synthetic test split.

    python training/eval_text_checks.py --n 120

Reports how often each field is read correctly, and how often genuine
receipts get a red flag (false alarms) vs. fakes.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from analysis.fields import analyse_text  # noqa: E402
from analysis.ocr import read_lines  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    d = ROOT / "data" / "synth" / "test"
    rows = list(csv.DictReader(open(d / "labels.csv", encoding="utf-8")))[: a.n]
    stats = Counter()
    flags = {"genuine": Counter(), "fake": Counter()}
    for r in rows:
        im = Image.open(d / "images" / r["file"])
        p = analyse_text(read_lines(im), im.height)
        kind = "fake" if r["fake"] == "True" else "genuine"
        stats[kind] += 1
        stats["receipt"] += p.is_receipt
        if kind == "genuine":
            stats["amount_ok"] += p.amount_value is not None and abs(p.amount_value - float(r["amount"])) < 0.01
            stats["utr_ok"] += p.utr == r["rrn"] or (p.utr or "").startswith(("SBIN", "HDFC", "ICIC", "UTIB", "KKBK", "BARB", "PUNB", "CNRB", "UBIN", "IDFB", "YESB", "IDIB", "FDRL", "BKID"))
            stats["date_ok"] += p.when is not None and p.when.strftime("%Y-%m-%d") == r["date"][:10]
        bad = [f.code for f in p.findings if f.kind == "bad"]
        stats[kind + "_flagged"] += bool(bad)
        for c in bad:
            flags[kind][c] += 1
        if a.verbose and bad and kind == "genuine":
            print("false alarm:", r["file"], r["layout"], bad, p.summary())
    g = stats["genuine"]
    report = {
        "images": len(rows),
        "recognised_as_receipt": stats["receipt"] / len(rows),
        "genuine_amount_read": stats["amount_ok"] / g,
        "genuine_utr_read": stats["utr_ok"] / g,
        "genuine_date_read": stats["date_ok"] / g,
        "genuine_with_red_flag": stats["genuine_flagged"] / g,
        "fake_with_red_flag": stats["fake_flagged"] / stats["fake"],
        "red_flags_on_genuine": dict(flags["genuine"]),
        "red_flags_on_fake": dict(flags["fake"]),
    }
    print(json.dumps(report, indent=2))
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "models" / "text_checks_metrics.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
