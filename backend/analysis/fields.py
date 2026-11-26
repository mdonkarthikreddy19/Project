"""
Reads the text of a receipt and checks whether the pieces agree with each other.

Most fake screenshots are edited by hand, and people rarely keep every
field consistent. The strongest checks here:

* A UPI UTR/RRN is 12 digits and starts with the date it was issued:
  last digit of the year, day of the year (001-366), then the hour.
  6330 10 xxxxxx  ->  2026, day 330 (26 Nov), 10 o'clock.
  An invented number almost never lines up with the printed date.
* PhonePe-style transaction IDs carry the full timestamp (T + yymmddHHMMSS).
* NEFT UTRs carry the year digit and day of year after the bank code.
* Dates that don't exist, dates in the future, wrong weekday.
* The same amount printed twice with different values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .findings import Finding
from .ocr import Line

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MON_RE = "(" + "|".join(MONTHS) + ")[a-z]*"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# UPI handles seen on live PSP apps. Not exhaustive - an unknown handle is only a note.
KNOWN_HANDLES = {
    "okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "ibl", "axl", "paytm", "ptyes", "ptaxis",
    "pthdfc", "ptsbi", "upi", "apl", "yapl", "rapl", "abfspay", "axisbank", "axisb", "sbi", "icici",
    "hdfcbank", "hdfcbankjd", "kotak", "kbl", "fbl", "federal", "ikwik", "freecharge", "jupiteraxis",
    "naviaxis", "slc", "waicici", "waaxis", "wahdfcbank", "wasbi", "postbank", "pnb", "barodampay",
    "boi", "cnrb", "unionbank", "unionbankofindia", "uboi", "idfcbank", "idfcfirst", "idfc", "yesbank",
    "yesbankltd", "aubank", "rbl", "idbi", "indus", "indianbank", "iob", "centralbank", "cboi", "dbs",
    "dlb", "equitas", "esaf", "fino", "jsb", "kvb", "kaypay", "mahb", "pingpay", "pockets", "psb",
    "sib", "tjsb", "uco", "ujjivan", "united", "utbi", "vijb", "airtel", "airtelpaymentsbank", "jio",
    "mairtel", "okbizaxis", "timecosmos", "tapicici", "superyes", "sliceaxis", "goaxb", "oneyes",
    "kmbl", "hsbc", "citi", "citigold", "sc", "nsdl", "jupiter", "fam", "ezeepay", "bhim", "abcdicici",
    "axisbankltd", "mbk", "zoicici", "yesg", "dbsbank", "hdfc", "pz", "pty", "icicibank",
}

SUCCESS_WORDS = ["successful", "success", "completed", "paidsuccessfully", "moneysent", "sentsuccessfully",
                 "processed", "paymentdone", "transfersuccessful", "debited"]
PENDING_WORDS = ["pending", "processing", "inprogress", "awaitingconfirmation", "underprocess"]
FAILED_WORDS = ["failed", "declined", "unsuccessful", "reversed", "cancelled", "canceled", "rejected"]

UTR_LABELS = ["upitransactionid", "upirefno", "upirefid", "upiref", "utrno", "utrnumber", "utr", "rrn",
              "bankreferenceno", "bankrefno", "referencenumber", "referenceno", "refno", "impsrefno",
              "transactionreferenceno", "transactionrefno"]


@dataclass
class Parsed:
    is_receipt: bool = False
    app: str = "Unknown"
    status: str | None = None
    amount: str | None = None
    amount_value: float | None = None
    when: datetime | None = None
    when_text: str | None = None
    utr: str | None = None
    txn_id: str | None = None
    payee: str | None = None
    vpa: str | None = None
    has_time: bool = False
    tid: re.Match | None = None
    boxes: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    def summary(self):
        return {
            "app": self.app,
            "status": self.status,
            "amount": self.amount,
            "date": self.when.strftime("%d %b %Y, %I:%M %p") if self.when else self.when_text,
            "utr": self.utr,
            "transaction_id": self.txn_id,
            "paid_to": self.payee,
            "upi_id": self.vpa,
        }


# ------------------------------------------------------------------ helpers

def _digitish(s: str) -> str:
    """OCR often reads 0 as O and 1 as l/I inside long numbers."""
    letters = sum(c.isalpha() for c in s)
    if len(s) >= 8 and letters <= 2 and sum(c.isdigit() for c in s) / len(s) >= 0.75:
        return s.translate(str.maketrans({"o": "0", "O": "0", "l": "1", "I": "1", "i": "1", "s": "5", "S": "5"}))
    return s


def _same_row(a: Line, b: Line) -> bool:
    ov = min(a.box[3], b.box[3]) - max(a.box[1], b.box[1])
    return ov > 0.5 * min(a.height, b.height)


def _value_after_label(lines: list[Line], i: int, label_end: int) -> tuple[str, Line] | None:
    """The value for a label is either later on the same line, on the same row, or on the next line."""
    rest = lines[i].squashed[label_end:].lstrip(":.-#")
    if len(rest) >= 6:
        return rest, lines[i]
    for j in range(i + 1, min(i + 3, len(lines))):
        if _same_row(lines[i], lines[j]) or lines[j].box[1] > lines[i].box[1]:
            return lines[j].squashed.lstrip(":.-#"), lines[j]
    return None


# ------------------------------------------------------------------ date and time

def _year(y: str) -> int:
    y = int(y)
    return y + 2000 if y < 100 else y


def _find_date(text: str):
    """Returns (day, month, year, start, end) without validating the day."""
    text = text.replace("0ct", "oct").replace("n0v", "nov").replace("0ec", "dec").replace("de0", "dec")
    pats = [
        (rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s,\-.']*{MON_RE}[\s,\-.']*(\d{{4}}|\d{{2}}(?!\d))", "dmy"),
        (rf"{MON_RE}[\s.\-]*(\d{{1,2}})(?:st|nd|rd|th)?[\s,]*(\d{{4}})", "mdy"),
        (r"(\d{4})-(\d{2})-(\d{2})", "iso"),
        (r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2}(?!\d))", "num"),
    ]
    for pat, kind in pats:
        m = re.search(pat, text)
        if not m:
            continue
        g = m.groups()
        if kind == "dmy":
            return int(g[0]), MONTHS.index(g[1]) + 1, _year(g[2]), m.start(), m.end()
        if kind == "mdy":
            return int(g[1]), MONTHS.index(g[0]) + 1, _year(g[2]), m.start(), m.end()
        if kind == "iso":
            return int(g[2]), int(g[1]), int(g[0]), m.start(), m.end()
        d, mo = int(g[0]), int(g[1])
        if mo > 12 and d <= 12:  # written month-first
            d, mo = mo, d
        return d, mo, _year(g[2]), m.start(), m.end()
    return None


def _find_time(text: str):
    m = re.search(r"(?<!\d)(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    sec = int(m.group(3)) if m.group(3) else None
    ap = (m.group(4) or "").replace(".", "")
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h, mi, sec, bool(ap), m.start()


def parse_when(lines: list[Line], img_h: float, out: Parsed):
    top_cut = img_h * 0.045  # ignore the phone's own clock in the status bar
    for i, ln in enumerate(lines):
        t = ln.squashed
        found = _find_date(t)
        if not found or ln.box[3] < top_cut:
            continue
        d, mo, y, s, e = found
        out.when_text = ln.text
        out.boxes["date"] = ln.box
        tm = _find_time(t[e:]) or _find_time(t[:s])
        if tm is None:
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and lines[j].box[3] > top_cut and _find_date(lines[j].squashed) is None:
                    tm = _find_time(lines[j].squashed)
                    if tm:
                        break
        try:
            base = datetime(y, mo, d)
        except ValueError:
            out.findings.append(Finding(
                "date_invalid", "The date doesn't exist",
                f"The receipt shows day {d} of month {mo}, {y}. No app would print an impossible date, so this was almost certainly typed in.",
                3.0))
            return
        h, mi, sec = (tm[0], tm[1], tm[2]) if tm else (0, 0, None)
        if h > 23 or mi > 59 or (sec is not None and sec > 59):
            out.findings.append(Finding("time_invalid", "The time isn't a real time",
                                        f"The receipt shows {tm[0]}:{tm[1]:02d}.", 2.5))
            return
        out.when = base.replace(hour=h, minute=mi, second=sec or 0) if tm else base
        out.has_time = tm is not None
        wd = re.search(r"(?<![a-z])(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?[,|\s]*$", t[:s])
        if wd and WEEKDAYS.index(wd.group(1)) != base.weekday():
            out.findings.append(Finding(
                "weekday", "Weekday doesn't match the date",
                f"It says {wd.group(1).title()}, but {base:%d %b %Y} was a {base:%A}.", 2.5))
        now = datetime.now()
        if out.when > now + timedelta(days=1):
            out.findings.append(Finding("future", "Date is in the future",
                                        f"The receipt is dated {out.when:%d %b %Y}, which hasn't happened yet.", 3.0))
        return


# ------------------------------------------------------------------ reference numbers

def parse_refs(lines: list[Line], out: Parsed):
    labelled = None
    for i, ln in enumerate(lines):
        t = ln.squashed
        for lab in UTR_LABELS:
            k = t.find(lab)
            if k < 0:
                continue
            got = _value_after_label(lines, i, k + len(lab))
            if got:
                val = _digitish(re.sub(r"[^0-9a-z]", "", got[0]))
                num = re.search(r"\d{12}", val)
                if num:
                    val = num.group(0)
                if len(val) >= 6:
                    labelled = (val, got[1])
            break
        if labelled:
            break

    all_text = [(ln, _digitish(re.sub(r"[^0-9a-z]", " ", ln.squashed))) for ln in lines]
    twelve = [(m.group(0), ln) for ln, t in all_text for m in re.finditer(r"(?<![0-9a-z])\d{12}(?![0-9a-z])", t)]

    if labelled:
        val, ln = labelled
        out.utr = val.upper() if not val.isdigit() else val
        out.boxes["utr"] = ln.box
    elif twelve:
        out.utr, ln = twelve[0]
        out.boxes["utr"] = ln.box

    # transaction-ID formats that carry a timestamp
    for ln in lines:
        t = _digitish(ln.squashed)
        m = re.search(r"(?<![a-z0-9])t(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{4,14})(?!\d)", t)
        if m:
            out.txn_id = "T" + m.group(0)[1:]
            out.boxes["txn_id"] = ln.box
            out.tid = m
            break
        m = re.search(r"cicag[a-z0-9_\-]{6,}", ln.squashed)
        if m and not out.txn_id:
            g = re.search(r"CICAg[\w\-]+", ln.text.replace(" ", ""), re.I)
            out.txn_id = g.group(0) if g else m.group(0)
            out.boxes["txn_id"] = ln.box


def check_refs(out: Parsed):
    f = out.findings
    u = out.utr
    if u is None:
        if out.txn_id:
            f.append(Finding("no_utr", "No UTR shown",
                             "There's an app transaction ID but no UTR. Cashback and wallet credits look like this.", 0.1))
            return
        if out.app in ("Google Pay", "PhonePe", "Paytm", "UPI app"):
            f.append(Finding("no_utr", "No UTR / reference number found",
                             "Every completed UPI payment has a 12-digit UTR. Screenshots that crop it out, or never had one, deserve suspicion.", 0.8))
        elif out.app.startswith("Bank"):
            f.append(Finding("no_utr", "No reference number found",
                             "Bank transfer receipts normally show a UTR or reference number.", 0.8))
        return

    neft = re.fullmatch(r"([a-z]{4})n(\d)(\d{3})(\d{5,})", u.lower())
    rtgs = re.fullmatch(r"([a-z]{4})r(\d{4})(\d{2})(\d{2})(\d{5,})", u.lower())
    if neft or rtgs:
        _check_bank_utr(out, neft, rtgs)
        return
    if not u.isdigit():
        if out.app != "Bank transfer":
            f.append(Finding("utr_letters", "UTR contains letters",
                             f"The UTR reads '{u}'. UPI UTRs are digits only.", 0.9))
        return
    if len(u) != 12:
        f.append(Finding("utr_length", "UTR is the wrong length",
                         f"'{u}' has {len(u)} digits. A UPI UTR always has exactly 12.", 2.4))
        return

    # Real UTRs from Google Pay, PhonePe and Paytm (669601348390, 252700316474, 319364546998...)
    # don't encode the payment date, so beyond "12 digits" there is nothing safe to check.
    f.append(Finding("utr_ok", "UTR has the right format", "12 digits, like every UPI reference number.", -0.2))


def _check_bank_utr(out: Parsed, neft, rtgs):
    w = out.when
    if w is None:
        return
    if neft:
        y, ddd = int(neft.group(2)), int(neft.group(3))
        ok = y == w.year % 10 and abs(ddd - w.timetuple().tm_yday) <= 2
        what = f"year …{y}, day {ddd}"
    else:
        try:
            d = datetime(int(rtgs.group(2)), int(rtgs.group(3)), int(rtgs.group(4)))
            ok = abs((d.date() - w.date()).days) <= 2
            what = f"{d:%d %b %Y}"
        except ValueError:
            ok, what = False, "an impossible date"
    if ok:
        out.findings.append(Finding("bank_utr_match", "UTR matches the transfer date",
                                    f"The UTR encodes {what}, consistent with the receipt.", -0.6))
    else:
        out.findings.append(Finding("bank_utr_mismatch", "UTR doesn't match the transfer date",
                                    f"The UTR encodes {what} but the receipt is dated {w:%d %b %Y}.", 1.0))


def check_txn_id(out: Parsed):
    m = out.tid
    if not m or out.when is None:
        return
    try:
        stamp = datetime(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)),
                         int(m.group(4)), int(m.group(5)), int(m.group(6)))
    except ValueError:
        out.findings.append(Finding("tid_invalid", "Transaction ID has an impossible timestamp",
                                    f"{out.txn_id} should start with T + date + time, but the date in it doesn't exist.", 1.8))
        return
    diff = abs((stamp - out.when).total_seconds())
    if diff <= 180 or (not out.has_time and stamp.date() == out.when.date()):
        out.findings.append(Finding("tid_match", "Transaction ID matches the time",
                                    f"The ID is stamped {stamp:%d %b %Y %H:%M:%S}, same as the receipt.", -0.6))
    elif stamp.date() == out.when.date():
        out.findings.append(Finding("tid_time", "Transaction ID time is off",
                                    f"The ID is stamped {stamp:%H:%M}, the receipt says {out.when:%H:%M}.", 1.0))
    else:
        out.findings.append(Finding("tid_mismatch", "Transaction ID doesn't match the date",
                                    f"The ID is stamped {stamp:%d %b %Y} but the receipt says {out.when:%d %b %Y}.", 1.6))


# ------------------------------------------------------------------ amount

AMOUNT_NUM = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
# the OCR model often reads the rupee sign as 天 or z
RUPEE_LIKE = "₹天z%?&"
CURRENCY = r"(?:₹|天|rs\.?|inr|(?<![a-z0-9])z(?=\d)|(?<=of)[?&](?=\d))"
IGNORE_AMOUNT_CTX = ["cashback", "reward", "fee", "charge", "balance", "saved", "offer", "won", "limit", "scratch"]


def _amount_value(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_amount(lines: list[Line], img_h: float, out: Parsed):
    cands = []  # (text, value, line, tagged)
    for i, ln in enumerate(lines):
        if ln.box[3] < img_h * 0.045:
            continue
        raw = ln.text.replace(" ", "")
        low = raw.lower()
        for m in re.finditer(CURRENCY + r":?" + AMOUNT_NUM, low):
            cands.append((m.group(1), ln, True))
        # "Total: ₹24.00" where OCR turned the rupee sign into F, # or T
        m = re.search(r"(?:total|amount)[^0-9a-z]{0,3}[a-z#]?[^0-9a-z]{0,2}([0-9][0-9,]*\.[0-9]{2})", low)
        if m and not any(c[1] is ln for c in cands):
            cands.append((m.group(1), ln, True))
        # big bare number line, e.g. the headline amount where OCR dropped the ₹
        m = re.fullmatch(f"[{RUPEE_LIKE}]?" + r"([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{2})?|[0-9]{1,6}(?:\.[0-9]{2})?)", low)
        if m and not any(c[1] is ln for c in cands):
            # a leading ₹ (or the 天 OCR reads it as) still marks it as money
            cands.append((m.group(1), ln, low[:1] in ("₹", "天", "?", "&")))
        if "amount" in low:
            for j in range(i + 1, min(i + 3, len(lines))):
                mj = re.fullmatch(f"[{RUPEE_LIKE}]?" + r"(?:rs\.?|inr)?" + AMOUNT_NUM, lines[j].squashed)
                if mj and (_same_row(ln, lines[j]) or j == i + 1):
                    cands.append((mj.group(1), lines[j], True))
                    break
    cands = [(t, ln, tag) for t, ln, tag in cands if _amount_value(t) is not None and len(t.replace(",", "").split(".")[0]) <= 9]
    if not cands:
        return
    tagged = [c for c in cands if c[2]]
    if tagged:
        # a line that says total/amount wins, then the biggest text (the headline amount)
        main = max(tagged, key=lambda c: (any(w in c[1].squashed for w in ("total", "amount", "paid", "debited")),
                                          c[1].height, -c[1].box[1]))
    else:
        # no currency marker anywhere: only trust a bare number if it's clearly the headline
        # "1,649.15" is money-shaped even without its ₹; a plain "364873" could be anything
        shaped = [c for c in cands if "," in c[0] or re.search(r"\.\d\d$", c[0])]
        if shaped:
            main = max(shaped, key=lambda c: (c[1].height, -c[1].box[1]))
        else:
            heights = sorted(ln.height for ln in lines)
            median = heights[len(heights) // 2]
            main = max(cands, key=lambda c: (c[1].height, -c[1].box[1]))
            if main[1].height < median * 1.6:
                return
    out.amount_value = _amount_value(main[0])
    out.amount = "₹" + main[0]
    out.boxes["amount"] = main[1].box

    fmt = main[0].split(".")[0]
    indian = re.fullmatch(r"\d{1,2}(,\d{2})*,\d{3}", fmt)
    intl = re.fullmatch(r"\d{1,3}(,\d{3})+", fmt)
    if "," in fmt and not (indian or intl):
        out.findings.append(Finding("amount_commas", "Commas in the amount are in the wrong places",
                                    f"'{main[0]}' isn't how any payment app groups digits. Commas usually shift when a digit is added or removed by hand.", 1.6))
    if "." in main[0] and len(main[0].split(".")[1]) == 1:
        out.findings.append(Finding("amount_decimals", "Amount has one decimal digit",
                                    f"'{main[0]}' - apps always print paise with two digits.", 0.9))

    others = {}
    for t, ln, tag in cands:
        v = _amount_value(t)
        if ln is main[1] or not tag or v == out.amount_value:
            continue
        if any(w in ln.squashed for w in IGNORE_AMOUNT_CTX):
            continue
        others[v] = t
    if others:
        o = next(iter(others.values()))
        out.findings.append(Finding("amount_conflict", "The amount appears twice with different values",
                                    f"Headline says ₹{main[0]} but elsewhere it says ₹{o}. Edits often change one copy and miss the other.", 2.2))


# ------------------------------------------------------------------ the rest

def parse_misc(lines: list[Line], out: Parsed):
    text = " ".join(ln.squashed for ln in lines)
    if "googletransactionid" in text or "googlepay" in text or "gpay" in text:
        out.app = "Google Pay"
    elif "phonepe" in text or ("transferdetails" in text and re.search(r"t\d{20}", text)):
        out.app = "PhonePe"
    elif "paytm" in text or ("upirefno" in text and "orderid" in text):
        out.app = "Paytm"
    elif "bhim" in text:
        out.app = "BHIM"
    elif "amazonpay" in text:
        out.app = "Amazon Pay"
    elif any(w in text for w in ("neft", "rtgs", "imps", "beneficiary", "fundstransfer", "ifsc")):
        out.app = "Bank transfer"
    elif "upi" in text and any(w in text for w in ("transactionid", "paidto", "utr", "upiid", "upiref", "sentto",
                                                    "debitedfrom", "paymentsuccessful", "moneysent")):
        out.app = "UPI app"
    elif "upi" in text:
        # a printed bill or ticket that was paid by UPI, not an app screen
        out.app = "Paid by UPI (printed)"

    for words, status in ((FAILED_WORDS, "Failed"), (PENDING_WORDS, "Pending"), (SUCCESS_WORDS, "Successful")):
        hit = next((ln for ln in lines for w in words if w in ln.squashed), None)
        if hit:
            out.status = status
            out.boxes["status"] = hit.box
            break
    if out.status in ("Failed", "Pending"):
        out.findings.append(Finding("status_" + out.status.lower(), f"Receipt itself says {out.status.lower()}",
                                    "This screen does not show a completed payment. Don't release goods against it.", 1.8))

    m = re.search(r"([a-z0-9][a-z0-9.\-_]{1,})@([a-z]{2,})", text)
    if m:
        handle = m.group(2)
        if handle not in ("gmail", "yahoo", "outlook", "hotmail", "rediffmail"):
            out.vpa = m.group(0)
            for ln in lines:
                if m.group(0) in ln.squashed:
                    out.boxes["vpa"] = ln.box
                    break
            if handle not in KNOWN_HANDLES and not any(handle.startswith(h) for h in ("ok", "pt", "wa")):
                out.findings.append(Finding("vpa_handle", "Unfamiliar UPI handle",
                                            f"'@{handle}' isn't one of the common bank/app handles. It may be a newer bank, or a typo made while editing.", 0.3))

    for i, ln in enumerate(lines):
        mt = re.match(r"^(?:paid\s*to|sent\s*to|to)[:\s]*([A-Za-z][A-Za-z .&'-]{2,})$", ln.text, re.I)
        if mt and "@" not in ln.text:
            out.payee = mt.group(1).strip()
            out.boxes["payee"] = ln.box
            break
        if ln.squashed in ("paidto", "sentto", "to", "beneficiaryname") and i + 1 < len(lines):
            nxt = lines[i + 1]
            # a bare "to" is too common to trust unless a full name (two words) follows
            words = 2 if ln.squashed == "to" else 1
            if re.match(r"^[A-Za-z][A-Za-z .&'-]{2,}$", nxt.text) and len(nxt.text.split()) >= words:
                out.payee = nxt.text.strip()
                out.boxes["payee"] = nxt.box
                break


def analyse_text(lines: list[Line], img_h: float) -> Parsed:
    out = Parsed()
    if not lines:
        return out
    parse_misc(lines, out)
    parse_when(lines, img_h, out)
    parse_amount(lines, img_h, out)
    parse_refs(lines, out)
    signals = [out.amount is not None, out.utr is not None or out.txn_id is not None, out.status is not None,
               out.when is not None, out.vpa is not None, out.app != "Unknown"]
    out.is_receipt = sum(signals) >= 3
    if out.is_receipt:
        check_refs(out)
        check_txn_id(out)
        if out.when and out.when < datetime.now() - timedelta(days=365 * 2):
            out.findings.append(Finding("old", "Payment is over two years old",
                                        f"Dated {out.when:%d %b %Y}. Old receipts get reused as proof of new payments.", 0.4))
    return out
