# Payment receipt checker

Upload a screenshot of a UPI or bank payment (Google Pay, PhonePe, Paytm, BHIM, IMPS / NEFT / RTGS
receipts) or paste a link someone sent as "proof", and get a fake-likelihood percentage with the
reasons behind it.

It can't confirm a payment. Only your own bank or UPI app can do that. What it does is catch the
things edited and fake receipts usually get wrong.

## What it checks

**Screenshots**

| Check | Why it works |
|---|---|
| UTR format | A UPI UTR is exactly 12 digits. (Real Google Pay / PhonePe / Paytm UTRs do *not* encode the date, so no date check is done on them.) |
| Transaction-ID timestamp | PhonePe IDs start with `T` + `yymmddHHMMSS` (`T261015011327…` = 15 Oct 2026, 01:13:27) and must match the printed time. NEFT/RTGS UTRs carry the date too. |
| Dates | Impossible dates (31 Feb), wrong weekday, dates in the future. |
| Amount | The same amount printed twice with different values; commas in impossible places. |
| Status | Pending / failed receipts passed off as proof. |
| File metadata | Editor names (Photoshop, PicsArt, Snapseed, Canva…) in EXIF/XMP/PNG chunks; a screenshot timestamp older than the payment it shows. |
| Edited lines | A trained model (gradient-boosted trees, `analysis/line_features.py` + `line_model.py`) scores every OCR'd line of text against its neighbours: background fill and noise inside vs. just outside the line, straight seams left by an erase rectangle, error level and JPEG blockiness, ink colour, anti-aliasing and column alignment. Edited lines are outlined on the screenshot. |
| Edited pixels | An experimental CNN (`analysis/tamper_net.py`) that maps edits pixel by pixel. It only votes when `evaluate_model.py` shows it clearly beats chance on held-out data; otherwise only the error-level (ELA) view is shown. |

**Links**

Official bank / UPI-app domains (including the new `.bank.in` domains) vs. look-alikes, `upi://pay`
links disguised as receipts (these make *you* pay), shorteners, free site builders, cheap TLDs, bait
words, and pages that ask for a UPI PIN, OTP, password or card number. Redirects are followed
server-side with private-network addresses blocked.

Each check adds or removes evidence (log-odds). The sum becomes the percentage, clamped to 3-97%
because neither answer is ever certain.

## Layout

```
backend/            FastAPI app + analysis
  app.py            /api/check/image, /api/check/link, serves frontend/dist
  analysis/
    ocr.py          RapidOCR (ONNX, CPU)
    fields.py       reads amount / UTR / date / IDs and cross-checks them
    forensics.py    metadata, ELA, CNN inference, heat map
    line_features.py / line_model.py   per-line edit detector
    links.py        link checks
    tamper_net.py   CNN definition
  tests/            rule and link tests (no OCR needed)
frontend/           React + Vite UI
training/
  receipt_synth.py  renders receipts in GPay / PhonePe / Paytm / bank styles and tampers with them
  build_dataset.py  writes data/synth/{train,val,test}
  train_line_model.py  trains the per-line edit detector (CPU, ~15 min)
  train.py          trains the experimental CNN (GPU)
  evaluate_model.py picks the CNN threshold on val, reports on test
  eval_text_checks.py  measures OCR + consistency checks
models/             tamper_net.pt, calibration.json, metrics
```

## Running it

```
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. On a phone on the same Wi-Fi, use your PC's IP address
(`http://192.168.x.x:8000`).

For frontend work, run the backend as above and `npm run dev` in `frontend/` (it proxies `/api`).

## Training

```
python training/build_dataset.py --train 5000 --val 600 --test 800
python training/train_line_model.py
python training/train.py --epochs 10        # optional, GPU
python training/evaluate_model.py
```

On a GTX 1650 this takes roughly an hour. Keep `--amp` off on GTX 16xx cards: fp16 gives NaN losses there.

### About the training data

There's no public, labelled set of real vs. forged Indian payment receipts, and scraping other
people's real receipts would mean collecting their names, UPI IDs and account numbers. So the model is
trained on rendered receipts that follow the field layout and wording of the common apps and bank
receipts, then edited the way forgers do it (whole-field retype, single-digit change, copy-move,
splice from another receipt), and pushed through WhatsApp-style recompression and resizing.

That means the reported numbers are on synthetic data. Real-world accuracy is unknown until you test
on real samples. The quickest win is adding your own:

```
data/real/genuine/          untouched screenshots
data/real/fake/             edited screenshots
data/real/fake_masks/       same filename, white where the edit is
```

then rerun `train.py` and `evaluate_model.py`. A few hundred real examples will do more than anything else.

## Results so far

**Real screenshots** (`data/real/genuine/`, 11 genuine Google Pay, PhonePe and Paytm receipts): all 11 come out
"Looks genuine" (13-21%). Building this set fixed real-world problems the synthetic data never showed:
OCR reading "Oct" as "0ct" and the rupee sign as "?" or "&", "Copy" buttons glued onto UTRs,
Google transaction IDs with dashes, cashback receipts with no UTR, and logos/avatars/ads that
confused the line detector (it now only judges the lines carrying the amount, UTR, date, IDs and names).

**Synthetic test set**: see `models/pipeline_metrics.json`. Edited receipts that keep every number
consistent and only change the amount often still get through. Treat "Looks genuine" as
"nothing obviously wrong", never as proof.

**Real forgeries**: `training/evaluate_findit.py` runs the "Find it again!" receipt forgery set
(ICDAR 2023, L3i). The download server is slow and rate-limits, so only part of the test split was
fetched; finish it with `python training/evaluate_findit.py --fetch`.

Add more real screenshots (genuine in `data/real/genuine/`, edited ones plus masks in
`data/real/fake/` and `data/real/fake_masks/`) and rerun `python training/train_line_model.py`.
