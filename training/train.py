"""
Trains TamperNet on data/synth (and data/real if you add some).

    python training/train.py --epochs 14

Real samples are optional but they help a lot. Put them in:
    data/real/genuine/*.jpg|png       untouched screenshots
    data/real/fake/*.jpg|png          edited screenshots
    data/real/fake_masks/<same name>.png   white where it was edited
A fake without a mask is skipped - we need to know where the edit is.
"""
import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from analysis.tamper_net import TamperNet, image_logit  # noqa: E402

CROP = 320


def roc_auc_score(y, p):
    """Rank-based AUC (Mann-Whitney U); avoids pulling in scikit-learn."""
    y, p = np.asarray(y), np.asarray(p)
    order = p.argsort()
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    for v in np.unique(p):  # average ranks for ties
        m = p == v
        ranks[m] = ranks[m].mean()
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def load_split(split):
    d = ROOT / "data" / "synth" / split
    rows = []
    with open(d / "labels.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fake = r["fake"] == "True"
            m = d / "masks" / (Path(r["file"]).stem + ".png")
            rows.append((d / "images" / r["file"], m if fake else None, int(fake), r))
    return rows


def load_real():
    d = ROOT / "data" / "real"
    rows = []
    for p in sorted((d / "genuine").glob("*")) if (d / "genuine").exists() else []:
        rows.append((p, None, 0, {}))
    for p in sorted((d / "fake").glob("*")) if (d / "fake").exists() else []:
        m = d / "fake_masks" / (p.stem + ".png")
        if m.exists():
            rows.append((p, m, 1, {}))
    return rows


class Crops(Dataset):
    """Decodes a screenshot once and cuts `k` crops from it - decoding is the slow part."""

    def __init__(self, rows, k=4):
        self.rows = rows
        self.k = k

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        path, mpath, label, _ = self.rows[i]
        img = np.asarray(Image.open(path).convert("RGB"))
        H, W = img.shape[:2]
        mask = np.zeros((H, W), np.uint8)
        if mpath is not None:
            m = Image.open(mpath).convert("L")
            if m.size != (W, H):
                m = m.resize((W, H))
            mask = (np.asarray(m) > 127).astype(np.uint8)
        if H < CROP or W < CROP:
            ph, pw = max(0, CROP - H), max(0, CROP - W)
            img = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode="edge")
            mask = np.pad(mask, ((0, ph), (0, pw)))
            H, W = mask.shape
        ys, xs = np.nonzero(mask)
        iy, ix = ink_pixels(img)
        xs_out, ms_out = [], []
        for _ in range(self.k):
            x, m = self._crop(img, mask, ys, xs, iy, ix, H, W)
            xs_out.append(x)
            ms_out.append(m)
        return torch.stack(xs_out), torch.stack(ms_out)

    @staticmethod
    def _crop(img, mask, ys, xs, iy, ix, H, W):
        # Genuine and fake crops must be framed the same way. Fakes used to be centred on
        # the (mostly left-aligned) edited text while genuine crops were random, and the
        # model learned "text near the left border = fake". Now both centre on text.
        r = random.random()
        if len(ys) and r < 0.6:
            k = random.randrange(len(ys))
            cy, cx = ys[k], xs[k]
        elif len(iy) and r < 0.9:
            k = random.randrange(len(iy))
            cy, cx = iy[k], ix[k]
        else:
            cy, cx = random.randrange(H), random.randrange(W)
        cy += random.randint(-CROP // 3, CROP // 3)
        cx += random.randint(-CROP // 3, CROP // 3)
        y0 = int(np.clip(cy - CROP // 2, 0, H - CROP))
        x0 = int(np.clip(cx - CROP // 2, 0, W - CROP))
        x = img[y0:y0 + CROP, x0:x0 + CROP]
        m = mask[y0:y0 + CROP, x0:x0 + CROP]
        x = torch.from_numpy(x.copy()).permute(2, 0, 1).float() / 255
        m = torch.from_numpy(m.copy()).float()[None]
        return x, m


def ink_pixels(img, step=4):
    """Coordinates of text-ish pixels: far from the image's dominant background colour."""
    g = img[::step, ::step].mean(axis=2)
    bg = np.median(g)
    ys, xs = np.nonzero(np.abs(g - bg) > 60)
    return ys * step, xs * step


def targets(mask):
    frac = F.avg_pool2d(mask, TamperNet.STRIDE)
    pix = torch.clamp(frac * 2.5, 0, 1)
    img = (mask.flatten(1).sum(1) > 40).float()
    return pix, img


@torch.no_grad()
def score_full(net, path, device, max_side=2400):
    im = Image.open(path).convert("RGB")
    if max(im.size) > max_side:
        f = max_side / max(im.size)
        im = im.resize((int(im.width * f), int(im.height * f)), Image.BICUBIC)
    x = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1).float()[None].to(device) / 255
    lm = net(x)
    return torch.sigmoid(image_logit(lm.float())).item()


def evaluate(net, rows, device):
    net.eval()
    ys, ps = [], []
    for path, _, label, _ in rows:
        ps.append(score_full(net, path, device))
        ys.append(label)
    ys, ps = np.array(ys), np.array(ps)
    auc = roc_auc_score(ys, ps)
    best = max(((ps >= t) == ys).mean() for t in np.linspace(0.05, 0.95, 91))
    return auc, best, ys, ps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--workers", type=int, default=4)
    # GTX 16xx cards return NaNs under fp16 autocast, so mixed precision is opt-in
    ap.add_argument("--amp", action="store_true")
    ap.add_argument("--crops-per-image", type=int, default=4)
    ap.add_argument("--val-size", type=int, default=300)
    a = ap.parse_args()
    torch.manual_seed(0)
    random.seed(0)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_rows = load_split("train") + load_real()
    val_rows = load_split("val")[: a.val_size]
    ds = Crops(train_rows, k=a.crops_per_image)
    print(f"train {len(ds)} images x {a.crops_per_image} crops, val {len(val_rows)} images, device {device}", flush=True)

    # batch is counted in crops; each item already carries k of them
    dl = DataLoader(ds, batch_size=max(1, a.batch // a.crops_per_image), shuffle=True, num_workers=a.workers,
                    drop_last=True, persistent_workers=a.workers > 0, pin_memory=True)
    net = TamperNet().to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(dl), pct_start=0.15)
    use_amp = a.amp and device.type == "cuda"
    scaler = torch.amp.GradScaler(enabled=use_amp)
    out_dir = ROOT / "models"
    out_dir.mkdir(exist_ok=True)
    best_auc, history = -1, []

    for ep in range(a.epochs):
        net.train()
        t0, tot = time.time(), 0.0
        for step, (x, m) in enumerate(dl):
            x = x.flatten(0, 1).to(device, non_blocking=True)
            m = m.flatten(0, 1).to(device, non_blocking=True)
            pix_t, img_t = targets(m)
            with torch.autocast(device.type, enabled=use_amp):
                lm = net(x)
            lm = lm.float()[..., : pix_t.shape[2], : pix_t.shape[3]]
            pix_t = pix_t[..., : lm.shape[2], : lm.shape[3]]
            loss = F.binary_cross_entropy_with_logits(lm, pix_t, pos_weight=torch.tensor(3.0, device=device)) \
                + 0.5 * F.binary_cross_entropy_with_logits(image_logit(lm), img_t)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item()
            if step % 100 == 0:
                print(f"  ep {ep + 1} step {step}/{len(dl)} loss {loss.item():.4f}", flush=True)
        auc, acc, _, _ = evaluate(net, val_rows, device)
        history.append(dict(epoch=ep + 1, loss=tot / len(dl), val_auc=auc, val_acc=acc))
        print(f"epoch {ep + 1}: loss {tot / len(dl):.4f} val AUC {auc:.4f} acc {acc:.4f} ({time.time() - t0:.0f}s)", flush=True)
        if auc > best_auc:
            best_auc = auc
            torch.save(net.state_dict(), out_dir / "tamper_net.pt")
    (out_dir / "train_history.json").write_text(json.dumps(history, indent=2))
    print("best val AUC", best_auc)


if __name__ == "__main__":
    main()
