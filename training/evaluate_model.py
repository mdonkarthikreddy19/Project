"""
Picks the decision threshold on the validation split, then reports how the
tamper model does on the untouched test split.

    python training/evaluate_model.py

Writes models/calibration.json (used by the backend) and models/model_metrics.json.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from train import ROOT, load_split, roc_auc_score, score_full  # noqa: E402

sys.path.insert(0, str(ROOT / "backend"))
from analysis.tamper_net import TamperNet  # noqa: E402


def scores(net, rows, device):
    return np.array([score_full(net, r[0], device) for r in rows]), np.array([r[2] for r in rows])


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = TamperNet().to(device)
    net.load_state_dict(torch.load(ROOT / "models" / "tamper_net.pt", map_location=device, weights_only=True))
    net.eval()

    val = load_split("val")
    pv, yv = scores(net, val, device)
    # balanced accuracy, nudged toward fewer false alarms on genuine receipts
    best_t, best = 0.5, -1
    for t in np.linspace(0.05, 0.95, 181):
        tpr = (pv[yv == 1] >= t).mean()
        tnr = (pv[yv == 0] < t).mean()
        s = 0.45 * tpr + 0.55 * tnr
        if s > best:
            best_t, best = float(t), s
    test = load_split("test")
    pt, yt = scores(net, test, device)
    pred = pt >= best_t
    by_tamper, by_layout, by_fmt = defaultdict(list), defaultdict(list), defaultdict(list)
    for (path, _, label, meta), p, ok in zip(test, pt, pred == yt):
        if label:
            by_tamper[meta["tamper"].split("+")[0].split(":")[0]].append(ok)
        by_layout[meta["layout"]].append(ok)
        by_fmt[Path(path).suffix.lstrip(".") + ("_fake" if label else "_genuine")].append(ok)
    rate = lambda d: {k: round(float(np.mean(v)), 3) for k, v in sorted(d.items())}  # noqa: E731
    report = {
        "note": "Synthetic test split (receipts rendered by training/receipt_synth.py, never seen in training). "
                "Real-world accuracy is not measured by this.",
        "threshold": round(best_t, 3),
        "test_images": int(len(yt)),
        "test_auc": round(roc_auc_score(yt, pt), 4),
        "test_accuracy": round(float((pred == yt).mean()), 4),
        "fakes_caught": round(float(pred[yt == 1].mean()), 4),
        "genuine_false_alarms": round(float(pred[yt == 0].mean()), 4),
        "detection_by_edit_type": rate(by_tamper),
        "accuracy_by_layout": rate(by_layout),
        "accuracy_by_format": rate(by_fmt),
        "val_auc": round(roc_auc_score(yv, pv), 4),
    }
    # the backend only lets this model vote when it is clearly better than chance on unseen data
    use = report["test_auc"] >= 0.7
    report["enabled_in_backend"] = use
    (ROOT / "models" / "calibration.json").write_text(json.dumps({"threshold": round(best_t, 3), "use": use}, indent=2))
    (ROOT / "models" / "model_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
