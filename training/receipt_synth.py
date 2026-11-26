"""
Renders payment receipts that look like phone screenshots, and makes
tampered copies of them with a pixel mask of what was changed.

There is no public dataset of labelled real/forged UPI receipts (and
collecting other people's real receipts isn't something we should do),
so the tamper model is trained on these. The layouts copy the *structure*
of common UPI / IMPS / NEFT receipts - status line, big amount, payee,
VPA, a 12-digit UTR, masked account number - not any one app's branding.

Edits mimic what people actually do in phone editors and Photoshop:
retype a whole field, change a single digit, clone digits from elsewhere
in the same screenshot, or paste a piece from another screenshot.
"""
from __future__ import annotations

import io
import os
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

# (regular, bold) pairs that exist on a stock Windows install
FAMILIES = [
    ("segoeui.ttf", "segoeuib.ttf"),
    ("arial.ttf", "arialbd.ttf"),
    ("calibri.ttf", "calibrib.ttf"),
    ("tahoma.ttf", "tahomabd.ttf"),
    ("verdana.ttf", "verdanab.ttf"),
    ("trebuc.ttf", "trebucbd.ttf"),
    ("corbel.ttf", "corbelb.ttf"),
    ("LeelawUI.ttf", "LeelawUI.ttf"),
    ("bahnschrift.ttf", "bahnschrift.ttf"),
    ("gadugi.ttf", "gadugib.ttf"),
]
FAMILIES = [f for f in FAMILIES if (FONT_DIR / f[0]).exists() and (FONT_DIR / f[1]).exists()]

FIRST = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan", "Kavya", "Arjun", "Meera",
         "Suresh", "Pooja", "Karthik", "Divya", "Manoj", "Lakshmi", "Imran", "Fatima", "Harpreet",
         "Gurpreet", "Ravi", "Nisha", "Sandeep", "Deepa", "Ajay", "Swati", "Naveen", "Ritu", "Venkat",
         "Asha", "Jayesh", "Neha", "Siddharth", "Bhavna", "Mohan", "Rekha", "Abdul", "Shalini"]
LAST = ["Sharma", "Patel", "Reddy", "Nair", "Iyer", "Singh", "Gupta", "Khan", "Das", "Mehta",
        "Joshi", "Kumar", "Rao", "Menon", "Pillai", "Verma", "Chopra", "Bose", "Shetty", "Yadav",
        "Mishra", "Agarwal", "Naidu", "Kulkarni", "Banerjee", "Jain", "Thomas", "Fernandes"]
SHOPS = ["Sri Balaji Stores", "Annapurna Mess", "Green Leaf Pharmacy", "City Mobile Point",
         "Royal Bakers", "Lakshmi Textiles", "Fresh Mart", "Ganesh Electricals", "Om Sai Traders",
         "Hotel Saravana", "Metro Fuel Station", "Krishna Medicals", "Star Hardware"]
HANDLES = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "ibl", "axl", "paytm", "ptyes",
           "ptaxis", "pthdfc", "ptsbi", "upi", "apl", "yapl", "axisbank", "sbi", "icici",
           "hdfcbank", "kotak", "fbl", "ikwik", "freecharge", "jupiteraxis", "naviaxis", "waicici",
           "postbank", "pnb", "barodampay", "boi", "cnrb", "unionbank", "idfcbank", "yesbank"]
BANKS = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank",
         "Bank of Baroda", "Punjab National Bank", "Canara Bank", "Union Bank of India",
         "IDFC FIRST Bank", "Yes Bank", "Indian Bank", "Federal Bank", "Bank of India"]
IFSC_PREFIX = {"State Bank of India": "SBIN", "HDFC Bank": "HDFC", "ICICI Bank": "ICIC",
               "Axis Bank": "UTIB", "Kotak Mahindra Bank": "KKBK", "Bank of Baroda": "BARB",
               "Punjab National Bank": "PUNB", "Canara Bank": "CNRB", "Union Bank of India": "UBIN",
               "IDFC FIRST Bank": "IDFB", "Yes Bank": "YESB", "Indian Bank": "IDIB",
               "Federal Bank": "FDRL", "Bank of India": "BKID"}
NOTES = ["Rent", "Groceries", "Dinner", "Fees", "Advance", "Repair", "Thanks", "Order 4471",
         "Electricity", "Petrol", "Tuition", "Gift", "Loan", "Milk", "", "", "", ""]


# ---------------------------------------------------------------- values

def indian_group(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def fmt_amount(value: float, rng: random.Random, symbol: str) -> str:
    rupees = int(value)
    paise = int(round((value - rupees) * 100))
    body = indian_group(rupees)
    if paise or rng.random() < 0.35:
        body += f".{paise:02d}"
    sep = " " if rng.random() < 0.3 else ""
    return f"{symbol}{sep}{body}"


def make_rrn(dt: datetime, rng: random.Random) -> str:
    # NPCI RRN: last digit of year, julian day, hour, 6-digit sequence
    return f"{dt.year % 10}{dt.timetuple().tm_yday:03d}{dt.hour:02d}{rng.randrange(10**6):06d}"


def make_txn_id(dt: datetime, rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.4:
        return "T" + dt.strftime("%y%m%d%H%M%S") + "".join(rng.choices(string.digits, k=rng.choice([8, 9, 10])))
    if kind < 0.7:
        chars = string.ascii_letters + string.digits
        return "CICAg" + "".join(rng.choices(chars, k=rng.choice([13, 15, 17])))
    return "".join(rng.choices(string.ascii_uppercase, k=3)) + "".join(rng.choices(string.digits, k=rng.choice([15, 17, 19])))


def fmt_date(dt: datetime, rng: random.Random) -> str:
    h12 = dt.strftime("%I").lstrip("0")
    ampm = dt.strftime("%p")
    if rng.random() < 0.5:
        ampm = ampm.lower()
    styles = [
        f"{dt.day} {dt:%b %Y}, {h12}:{dt:%M} {ampm}",
        f"{h12}:{dt:%M} {ampm} on {dt.day} {dt:%b %Y}",
        f"{dt:%d/%m/%Y %H:%M:%S}",
        f"{dt:%b} {dt.day}, {dt:%Y} at {h12}:{dt:%M} {ampm}",
        f"{dt:%a}, {dt.day} {dt:%b %Y} | {h12}:{dt:%M} {ampm}",
        f"{dt:%d %B %Y}, {dt:%H:%M}",
        f"{dt:%d-%m-%Y} {h12}:{dt:%M}:{dt:%S} {ampm}",
    ]
    return rng.choice(styles)


@dataclass
class Values:
    dt: datetime
    amount: float
    payee: str
    payee_vpa: str
    payer: str
    payer_bank: str
    acct_last4: str
    rrn: str
    txn_id: str
    note: str
    ifsc: str

    @staticmethod
    def random(rng: random.Random) -> "Values":
        now = datetime(2026, 11, 26, 12, 0)
        dt = now - timedelta(minutes=rng.randrange(60 * 24 * 700))
        dt = dt.replace(second=rng.randrange(60))
        amount = round(10 ** rng.uniform(1, 5.3), rng.choice([0, 0, 0, 2]))
        if rng.random() < 0.5:
            amount = float(int(amount // 10 * 10) or 10)
        if rng.random() < 0.3:
            payee = rng.choice(SHOPS)
        else:
            payee = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        handle_name = payee.split()[0].lower() + rng.choice(["", str(rng.randrange(10, 9999)), "." + payee.split()[-1].lower()])
        if rng.random() < 0.25:
            handle_name = "".join(rng.choices(string.digits, k=10))
        bank = rng.choice(BANKS)
        return Values(
            dt=dt, amount=amount, payee=payee,
            payee_vpa=f"{handle_name}@{rng.choice(HANDLES)}",
            payer=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            payer_bank=bank,
            acct_last4=f"{rng.randrange(10000):04d}",
            rrn=make_rrn(dt, rng), txn_id=make_txn_id(dt, rng),
            note=rng.choice(NOTES),
            ifsc=IFSC_PREFIX[bank] + "0" + f"{rng.randrange(10**6):06d}",
        )


# ---------------------------------------------------------------- drawing

@dataclass
class TextItem:
    text: str
    bbox: tuple
    font_path: str
    size: int
    fill: tuple
    xy: tuple
    anchor: str
    field: str | None


@dataclass
class Receipt:
    image: Image.Image
    items: list[TextItem] = field(default_factory=list)
    bg: tuple = (255, 255, 255)
    values: Values | None = None
    layout: str = ""


_font_cache: dict = {}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONT_DIR / path), size)
    return _font_cache[key]


def has_rupee(path: str) -> bool:
    f = font(path, 40)
    a = f.getmask("\u20b9").getbbox()
    b = f.getmask("\uffff").getbbox()
    return a is not None and a != b


class Canvas:
    def __init__(self, w: int, h: int, bg, scale: float):
        self.img = Image.new("RGB", (w, h), bg)
        self.d = ImageDraw.Draw(self.img)
        self.s = scale
        self.items: list[TextItem] = []
        self.bg = bg

    def px(self, v: float) -> int:
        return int(round(v * self.s))

    def text(self, x, y, text, path, size, fill, anchor="la", fieldname=None):
        if not text:
            return None
        f = font(path, self.px(size))
        xy = (self.px(x), self.px(y))
        self.d.text(xy, text, font=f, fill=fill, anchor=anchor)
        bb = self.d.textbbox(xy, text, font=f, anchor=anchor)
        item = TextItem(text, bb, path, self.px(size), fill, xy, anchor, fieldname)
        self.items.append(item)
        return item

    def rect(self, box, fill, radius=0):
        b = [self.px(v) for v in box]
        if radius:
            self.d.rounded_rectangle(b, radius=self.px(radius), fill=fill)
        else:
            self.d.rectangle(b, fill=fill)

    def check_badge(self, cx, cy, r, color, fg=(255, 255, 255)):
        c = (self.px(cx), self.px(cy))
        rr = self.px(r)
        self.d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], fill=color)
        w = max(2, self.px(r * 0.18))
        pts = [(c[0] - rr * 0.45, c[1] + rr * 0.02), (c[0] - rr * 0.1, c[1] + rr * 0.38), (c[0] + rr * 0.48, c[1] - rr * 0.32)]
        self.d.line(pts, fill=fg, width=w, joint="curve")

    def status_bar(self, fg, path, rng):
        t = f"{rng.randrange(1, 13)}:{rng.randrange(60):02d}"
        self.text(28, 14, t, path, 15, fg)
        x = 700
        bw = 26
        self.d.rounded_rectangle([self.px(x - bw), self.px(18), self.px(x), self.px(30)], radius=self.px(3), outline=fg, width=max(1, self.px(1.5)))
        lvl = rng.uniform(0.2, 1)
        self.d.rectangle([self.px(x - bw + 3), self.px(21), self.px(x - bw + 3 + (bw - 6) * lvl), self.px(27)], fill=fg)
        for i in range(4):
            hh = 4 + i * 3
            self.rect((640 + i * 6, 31 - hh, 643 + i * 6, 31), fg)


def palette(rng: random.Random):
    dark = rng.random() < 0.22
    hue_colors = [(0, 160, 90), (33, 150, 83), (95, 37, 159), (0, 102, 204), (16, 112, 74),
                  (220, 80, 20), (0, 186, 242), (30, 30, 30), (60, 64, 67), (103, 58, 183)]
    accent = rng.choice(hue_colors)
    if dark:
        bg = rng.choice([(18, 18, 18), (32, 33, 36), (12, 14, 20), (28, 28, 30)])
        fg = (235, 235, 235)
        sub = (160, 164, 170)
        card = tuple(min(255, c + 14) for c in bg)
    else:
        bg = rng.choice([(255, 255, 255), (248, 249, 250), (245, 245, 247), (250, 250, 250), (241, 243, 244)])
        fg = rng.choice([(20, 20, 20), (32, 33, 36), (33, 37, 41), (0, 0, 0)])
        sub = rng.choice([(95, 99, 104), (110, 110, 115), (117, 117, 117), (90, 90, 90)])
        card = (255, 255, 255) if bg != (255, 255, 255) else (247, 248, 250)
    return dict(dark=dark, bg=bg, fg=fg, sub=sub, card=card, accent=accent)


# ---- app-style layouts. These follow the field order and wording that the
# big UPI apps and bank net-banking receipts use, so OCR checks and the tamper
# model see realistic text placement. No logos or artwork are reproduced.

def _gpay_style(cv, v, rng, pal, reg, bold, amt, date):
    fg, sub = pal["fg"], pal["sub"]
    green = rng.choice([(30, 142, 62), (24, 128, 56), (52, 168, 83)])
    cv.text(360, 150, f"To {v.payee}", reg, 22, fg, "mt", "payee")
    cv.text(360, 190, amt, reg, rng.choice([56, 62, 66]), fg, "mt", "amount")
    cv.check_badge(300, 300, 14, green)
    cv.text(322, 300, "Completed", reg, 19, fg, "lm", "status")
    cv.rect((40, 336, 680, 338), tuple(int(c * 0.9 + b * 0.1) for c, b in zip(pal["bg"], fg)))
    cv.text(360, 352, date, reg, 18, sub, "mt", "date")
    y = 430
    cv.rect((24, y - 24, 696, y + 470), pal["card"], radius=16)
    rows = [("UPI transaction ID", v.rrn, "rrn"),
            ("To: " + v.payee, None, None),
            ("Google Pay • " + v.payee_vpa, None, "vpa"),
            (f"From: {v.payer} ({v.payer_bank})", None, "payer"),
            ("Google transaction ID", v.txn_id if v.txn_id.startswith("CICAg") else "CICAg" + v.txn_id[-15:], "txn_id")]
    for label, val, fname in rows:
        if val is None:
            cv.text(52, y, label, reg, 18, fg if fname != "vpa" else sub, "la", fname)
            y += 48
        else:
            cv.text(52, y, label, reg, 17, sub, "la")
            cv.text(52, y + 28, val, reg, 20, fg, "la", fname)
            y += 80
    cv.text(360, y + 40, "POWERED BY UPI", bold, 14, sub, "mt")


def _phonepe_style(cv, v, rng, pal, reg, bold, amt, date):
    fg, sub = pal["fg"], pal["sub"]
    head = rng.choice([(95, 37, 159), (103, 58, 183), (33, 150, 83)])
    cv.rect((0, 46, 720, 200), head)
    cv.check_badge(70, 123, 26, (255, 255, 255), fg=head)
    cv.text(116, 102, "Transaction Successful", bold, 24, (255, 255, 255), "la", "status")
    cv.text(116, 140, f"{v.dt:%I:%M %p}".lstrip("0").lower() + f" on {v.dt.day:02d} {v.dt:%b %Y}",
            reg, 16, (235, 230, 245), "la", "date")
    y = 236
    cv.rect((20, y - 16, 700, y + 170), pal["card"], radius=12)
    cv.text(40, y, "Paid to", reg, 16, sub, "la")
    cv.text(40, y + 34, v.payee, bold, 21, fg, "la", "payee")
    cv.text(40, y + 70, v.payee_vpa, reg, 16, sub, "la", "vpa")
    cv.text(680, y + 34, amt, bold, 23, fg, "ra", "amount")
    y += 210
    cv.rect((20, y - 16, 700, y + 280), pal["card"], radius=12)
    cv.text(40, y, "Transfer Details", bold, 19, fg, "la")
    tid = v.txn_id if v.txn_id.startswith("T") else "T" + v.dt.strftime("%y%m%d%H%M%S") + v.rrn[-9:]
    cv.text(40, y + 46, "Transaction ID", reg, 16, sub, "la")
    cv.text(40, y + 72, tid, bold, 18, fg, "la", "txn_id")
    cv.text(40, y + 122, "Debited from", reg, 16, sub, "la")
    cv.text(40, y + 148, f"XXXXXXXX{v.acct_last4}", bold, 18, fg, "la", "account")
    cv.text(680, y + 148, amt, reg, 18, fg, "ra")
    cv.text(40, y + 196, "UTR: " + v.rrn, reg, 17, sub, "la", "rrn")
    if v.note:
        cv.text(40, y + 236, "Message: " + v.note, reg, 16, sub, "la", "note")


def _paytm_style(cv, v, rng, pal, reg, bold, amt, date):
    fg, sub = pal["fg"], pal["sub"]
    blue = rng.choice([(0, 186, 242), (0, 46, 110), (0, 112, 192)])
    cv.check_badge(360, 160, 40, rng.choice([(33, 186, 69), blue]))
    cv.text(360, 225, rng.choice(["Paid Successfully", "Money Sent Successfully", "Payment Successful"]),
            bold, 22, fg, "mt", "status")
    cv.text(360, 270, amt, bold, rng.choice([50, 56]), fg, "mt", "amount")
    cv.text(360, 345, f"{v.dt:%I:%M %p}".lstrip("0") + f", {v.dt.day:02d} {v.dt:%b %Y}", reg, 17, sub, "mt", "date")
    y = 410
    cv.rect((24, y - 20, 696, y + 420), pal["card"], radius=14)
    cv.text(48, y, "To", reg, 16, sub, "la")
    cv.text(48, y + 26, v.payee, bold, 20, fg, "la", "payee")
    cv.text(48, y + 58, "UPI ID: " + v.payee_vpa, reg, 16, sub, "la", "vpa")
    cv.text(48, y + 110, "From", reg, 16, sub, "la")
    cv.text(48, y + 136, v.payer, bold, 20, fg, "la", "payer")
    cv.text(48, y + 168, f"{v.payer_bank} - {v.acct_last4}", reg, 16, sub, "la", "account")
    cv.text(48, y + 222, "UPI Ref No: " + v.rrn, reg, 17, fg, "la", "rrn")
    cv.text(48, y + 262, "Order ID: " + "".join(rng.choices(string.digits, k=rng.choice([16, 20]))), reg, 16, sub, "la", "txn_id")
    if v.note:
        cv.text(48, y + 302, "Note: " + v.note, reg, 16, sub, "la", "note")


def _neft_style(cv, v, rng, pal, reg, bold, amt, date):
    fg, sub, acc = pal["fg"], pal["sub"], pal["accent"]
    mode = rng.choice(["NEFT", "RTGS", "IMPS"])
    if mode == "NEFT":
        ref = IFSC_PREFIX[v.payer_bank] + "N" + f"{v.dt.year % 10}{v.dt.timetuple().tm_yday:03d}" + f"{rng.randrange(10**7):07d}"
    elif mode == "RTGS":
        ref = IFSC_PREFIX[v.payer_bank] + "R" + v.dt.strftime("%Y%m%d") + f"{rng.randrange(10**9):09d}"
    else:
        ref = v.rrn
    cv.text(36, 70, v.payer_bank, bold, 24, acc, "la")
    cv.text(36, 110, f"{mode} Transfer - Acknowledgement", bold, 20, fg, "la")
    cv.rect((36, 150, 684, 152), acc)
    y = 180
    rows = [("Status", rng.choice(["Success", "Completed", "Processed"]), "status"),
            ("UTR No." if mode != "IMPS" else "IMPS Ref No.", ref, "rrn"),
            ("Date & Time", date, "date"),
            ("Debit Account No.", f"XXXXXXXX{v.acct_last4}", "account"),
            ("Beneficiary Name", v.payee, "payee"),
            ("Beneficiary Account No.", f"XXXXXX{rng.randrange(10000):04d}", "benef_acct"),
            ("Beneficiary IFSC", v.ifsc, "ifsc"),
            ("Amount (INR)", amt.replace("₹", "").strip(), "amount"),
            ("Remarks", v.note or mode, "note")]
    for label, val, fname in rows:
        cv.text(36, y, label, reg, 16, sub, "la")
        cv.text(684, y, val, bold if fname in ("amount", "status") else reg, 17, fg, "ra", fname)
        cv.rect((36, y + 36, 684, y + 37), tuple(int(c * 0.88 + b * 0.12) for c, b in zip(pal["bg"], fg)))
        y += 56


APP_LAYOUTS = {"gpay": _gpay_style, "phonepe": _phonepe_style, "paytm": _paytm_style, "neft": _neft_style}
LAYOUTS = ["gpay", "gpay", "phonepe", "phonepe", "paytm", "paytm", "neft", "slip", "centered", "list"]


def render(rng: random.Random, values: Values | None = None, width: int | None = None) -> Receipt:
    v = values or Values.random(rng)
    reg, bold = rng.choice(FAMILIES)
    pal = palette(rng)
    W = width or rng.choice([540, 600, 720, 720, 864, 1080, 1080])
    s = W / 720
    H = int(W * rng.uniform(1.9, 2.25))
    cv = Canvas(W, H, pal["bg"], s)
    symbol = "\u20b9" if has_rupee(bold) and rng.random() < 0.85 else rng.choice(["Rs.", "Rs ", "INR "])
    amt = fmt_amount(v.amount, rng, symbol)
    date = fmt_date(v.dt, rng)
    layout = rng.choice(LAYOUTS)
    fg, sub, acc = pal["fg"], pal["sub"], pal["accent"]
    cv.status_bar(fg, reg, rng)

    if layout in APP_LAYOUTS:
        APP_LAYOUTS[layout](cv, v, rng, pal, reg, bold, amt, date)
    elif layout == "centered":
        top = 70
        if rng.random() < 0.5:
            cv.rect((0, 46, 720, 430), acc)
            fg_h, sub_h = (255, 255, 255), (230, 240, 235)
        else:
            fg_h, sub_h = fg, sub
        cv.check_badge(360, top + 70, 42, (255, 255, 255) if fg_h == (255, 255, 255) else acc,
                       fg=acc if fg_h == (255, 255, 255) else (255, 255, 255))
        cv.text(360, top + 140, rng.choice(["Payment successful", "Transaction Successful", "Paid successfully",
                                            "Money sent", "Payment Completed", "Sent successfully"]),
                bold, 24, fg_h, "mt", "status")
        cv.text(360, top + 185, amt, bold, rng.choice([48, 54, 60]), fg_h, "mt", "amount")
        cv.text(360, top + 262, f"to {v.payee}", reg, 21, sub_h, "mt", "payee")
        cv.text(360, top + 294, v.payee_vpa, reg, 18, sub_h, "mt", "vpa")
        y = 470
        cv.rect((24, y - 20, 696, y + 520), pal["card"], radius=18)
        rows = [("Date & time", date, "date"),
                (rng.choice(["UPI transaction ID", "UTR", "UPI Ref. No.", "UTR number"]), v.rrn, "rrn"),
                ("Transaction ID", v.txn_id, "txn_id"),
                ("From", v.payer, "payer"),
                (f"{v.payer_bank}", f"XXXXXX{v.acct_last4}", "account"),
                ("Note", v.note, "note")]
        for label, val, fname in rows:
            if not val:
                continue
            cv.text(52, y, label, reg, 17, sub, "la")
            cv.text(52, y + 28, val, bold if rng.random() < 0.5 else reg, 20, fg, "la", fname)
            y += 84
    elif layout == "list":
        cv.text(36, 70, rng.choice(["Transaction details", "Payment details", "Receipt"]), bold, 26, fg, "la")
        chip = acc
        cv.rect((36, 118, 250, 154), chip, radius=17)
        cv.text(143, 136, rng.choice(["SUCCESS", "Completed", "Successful"]), bold, 16, (255, 255, 255), "mm", "status")
        cv.text(36, 190, rng.choice(["Paid to", "Sent to", "To"]), reg, 17, sub, "la")
        cv.text(36, 216, v.payee, bold, 24, fg, "la", "payee")
        cv.text(36, 252, v.payee_vpa, reg, 18, sub, "la", "vpa")
        cv.text(684, 216, amt, bold, 34, fg, "ra", "amount")
        cv.rect((36, 300, 684, 302), tuple(int(c * 0.85 + b * 0.15) for c, b in zip(pal["bg"], fg)))
        y = 330
        rows = [("Transaction ID", v.txn_id, "txn_id"),
                (rng.choice(["UTR", "UTR No.", "UPI Ref ID", "Bank reference no."]), v.rrn, "rrn"),
                ("Debited from", f"{v.payer_bank} - {v.acct_last4}", "account"),
                ("Date", date, "date"),
                ("Remarks", v.note, "note")]
        for label, val, fname in rows:
            if not val:
                continue
            cv.text(36, y, label, reg, 17, sub, "la")
            cv.text(684, y, val, reg, 18, fg, "ra", fname)
            y += 62
    else:  # bank style e-receipt
        cv.rect((0, 46, 720, 140), acc)
        cv.text(36, 93, rng.choice(["Funds Transfer Receipt", "IMPS Transaction", "Transfer Successful", "e-Receipt"]),
                bold, 26, (255, 255, 255), "lm")
        y = 180
        cv.text(36, y, rng.choice(["Your transaction was successful", "Transaction completed successfully"]),
                bold, 20, acc, "la", "status")
        y += 60
        rows = [("Reference Number", v.rrn, "rrn"),
                ("Transaction Date", date, "date"),
                ("Amount", amt, "amount"),
                ("Beneficiary Name", v.payee, "payee"),
                ("Beneficiary A/c", f"XXXXXXXX{rng.randrange(10000):04d}", "benef_acct"),
                ("IFSC", v.ifsc, "ifsc"),
                ("Debit Account", f"XXXXXXXX{v.acct_last4}", "account"),
                ("Remarks", v.note or "IMPS", "note")]
        for i, (label, val, fname) in enumerate(rows):
            if i % 2 == 0:
                cv.rect((24, y - 14, 696, y + 40), pal["card"])
            cv.text(40, y, label, reg, 17, sub, "la")
            cv.text(380, y, val, bold if fname == "amount" else reg, 18, fg, "la", fname)
            y += 54

    if rng.random() < 0.6:
        cv.text(360, H / s - 70, rng.choice(["Powered by UPI", "Share receipt", "Done", "Check balance"]),
                reg, 16, sub, "mt")
    return Receipt(cv.img, cv.items, pal["bg"], v, layout)


# ---------------------------------------------------------------- saving pipeline

def jpeg_roundtrip(img: Image.Image, q: int, subsampling: int | None = None) -> Image.Image:
    buf = io.BytesIO()
    kw = {"quality": q}
    if subsampling is not None:
        kw["subsampling"] = subsampling
    img.save(buf, "JPEG", **kw)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def share_pipeline(img: Image.Image, rng: random.Random, mask: Image.Image | None = None):
    """What happens to a screenshot when it gets sent over WhatsApp, Telegram, email..."""
    if rng.random() < 0.25:
        f = rng.uniform(0.6, 0.95)
        size = (max(8, int(img.width * f)), max(8, int(img.height * f)))
        img = img.resize(size, Image.BICUBIC)
        if mask is not None:
            mask = mask.resize(size, Image.BILINEAR)
    buf = io.BytesIO()
    if rng.random() < 0.65:
        kw = {"quality": rng.randint(55, 95)}
        sub = rng.choice([None, 0, 2])
        if sub is not None:
            kw["subsampling"] = sub
        img.save(buf, "JPEG", **kw)
        fmt = "jpg"
    else:
        img.save(buf, "PNG", compress_level=3)
        fmt = "png"
    raw = buf.getvalue()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    return img, mask, fmt, raw


# ---------------------------------------------------------------- tampering

def border_color(img: np.ndarray, box) -> tuple:
    x0, y0, x1, y1 = box
    h, w = img.shape[:2]
    x0, y0 = max(0, x0 - 3), max(0, y0 - 3)
    x1, y1 = min(w - 1, x1 + 3), min(h - 1, y1 + 3)
    ring = np.concatenate([img[y0, x0:x1], img[y1, x0:x1], img[y0:y1, x0], img[y0:y1, x1]])
    return tuple(int(c) for c in np.median(ring, axis=0))


def pad(box, p, W, H):
    return (max(0, box[0] - p), max(0, box[1] - p), min(W, box[2] + p), min(H, box[3] + p))


def new_value(item: TextItem, rec: Receipt, rng: random.Random) -> str:
    t = item.text
    if item.field == "amount":
        digits = [i for i, c in enumerate(t) if c.isdigit()]
        out = list(t)
        if rng.random() < 0.5 and digits:
            out[digits[0]] = str(rng.randint(1, 9))
            if len(digits) > 1:
                out[digits[1]] = str(rng.randint(0, 9))
            return "".join(out)
        v = rec.values.amount * rng.choice([10, 5, 2, 3, 100])
        sym = "".join(c for c in t if not (c.isdigit() or c in ",.")).rstrip()
        return fmt_amount(v, rng, sym if sym.endswith((".", "\u20b9")) else sym + " " if sym else "\u20b9")
    if item.field in ("rrn", "txn_id", "account", "benef_acct", "ifsc"):
        return "".join(str(rng.randint(0, 9)) if c.isdigit() else c for c in t)
    if item.field == "date":
        return fmt_date(rec.values.dt + timedelta(days=rng.randint(1, 40), minutes=rng.randint(0, 600)), rng)
    if item.field in ("payee", "payer"):
        return rng.choice([f"{rng.choice(FIRST)} {rng.choice(LAST)}", rng.choice(SHOPS)])
    if item.field == "vpa":
        return f"{rng.choice(FIRST).lower()}{rng.randrange(100, 999)}@{rng.choice(HANDLES)}"
    if item.field == "status":
        return rng.choice(["Payment successful", "Transaction Successful", "SUCCESS", "Completed"])
    return t[::-1] if len(t) > 2 else t + "1"


def erase(img: Image.Image, box, color, rng: random.Random):
    mode = rng.random()
    d = ImageDraw.Draw(img)
    if mode < 0.55:
        d.rectangle(box, fill=color)
    elif mode < 0.8:
        jitter = tuple(int(np.clip(c + rng.randint(-5, 5), 0, 255)) for c in color)
        d.rectangle(box, fill=jitter)
    else:
        region = img.crop(box).filter(ImageFilter.GaussianBlur(rng.uniform(4, 9)))
        flat = Image.new("RGB", region.size, color)
        img.paste(Image.blend(region, flat, rng.uniform(0.6, 0.95)), box[:2])


def draw_text(img: Image.Image, xy, text, f, fill, anchor, aliased: bool):
    d = ImageDraw.Draw(img)
    if aliased:
        d.fontmode = "1"
    d.text(xy, text, font=f, fill=fill, anchor=anchor)
    return d.textbbox(xy, text, font=f, anchor=anchor)


def tamper_retype(rec: Receipt, img: Image.Image, mask: Image.Image, rng: random.Random):
    candidates = [i for i in rec.items if i.field]
    weights = [6 if i.field == "amount" else 2 if i.field in ("rrn", "date", "payee") else 1 for i in candidates]
    item = rng.choices(candidates, weights)[0]
    W, H = img.size
    arr = np.asarray(img)
    color = border_color(arr, item.bbox)
    text = new_value(item, rec, rng)
    # how the forger matched the original font
    r = rng.random()
    if r < 0.4:
        path, size = item.font_path, item.size
    elif r < 0.7:
        path, size = item.font_path, max(8, item.size + rng.choice([-3, -2, -1, 1, 2, 3]))
    else:
        fam = rng.choice(FAMILIES)
        path, size = rng.choice(fam), max(8, item.size + rng.randint(-2, 2))
    f = font(path, size)
    dx, dy = rng.randint(-3, 3), rng.randint(-3, 3)
    xy = (item.xy[0] + dx, item.xy[1] + dy)
    fill = item.fill if rng.random() < 0.6 else tuple(int(np.clip(c + rng.randint(-25, 25), 0, 255)) for c in item.fill)
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4))).textbbox(xy, text, font=f, anchor=item.anchor)
    ebox = pad((min(item.bbox[0], probe[0]), min(item.bbox[1], probe[1]),
                max(item.bbox[2], probe[2]), max(item.bbox[3], probe[3])), rng.randint(2, 8), W, H)
    erase(img, ebox, color, rng)
    tb = draw_text(img, xy, text, f, fill, item.anchor, aliased=rng.random() < 0.15)
    ImageDraw.Draw(mask).rectangle(ebox, fill=255)
    ImageDraw.Draw(mask).rectangle(pad(tb, 1, W, H), fill=255)
    return f"retype:{item.field}"


def tamper_digit(rec: Receipt, img: Image.Image, mask: Image.Image, rng: random.Random):
    """Change one or two digits in place - the most common real-world edit."""
    items = [i for i in rec.items if i.field in ("amount", "rrn", "date", "txn_id", "account") and i.anchor[0] == "l"
             and any(c.isdigit() for c in i.text)]
    if not items:
        return tamper_retype(rec, img, mask, rng)
    item = rng.choice(items)
    f = font(item.font_path, item.size)
    idx = [k for k, c in enumerate(item.text) if c.isdigit()]
    W, H = img.size
    arr = np.asarray(img)
    color = border_color(arr, item.bbox)
    for k in rng.sample(idx, min(len(idx), rng.choice([1, 1, 2]))):
        x = item.xy[0] + f.getlength(item.text[:k])
        w = f.getlength(item.text[k])
        box = pad((int(x), item.bbox[1], int(x + w) + 1, item.bbox[3]), 1, W, H)
        erase(img, box, color, rng)
        new = str((int(item.text[k]) + rng.randint(1, 9)) % 10)
        nf = f if rng.random() < 0.7 else font(rng.choice(rng.choice(FAMILIES)), item.size)
        tb = draw_text(img, (x + rng.choice([0, 0, 1, -1]), item.xy[1] + rng.choice([0, 0, 1, -1])), new, nf,
                       item.fill, "l" + item.anchor[1], aliased=rng.random() < 0.15)
        ImageDraw.Draw(mask).rectangle(pad((min(box[0], tb[0]), min(box[1], tb[1]), max(box[2], tb[2]), max(box[3], tb[3])), 1, W, H), fill=255)
    return f"digit:{item.field}"


def tamper_copymove(rec: Receipt, img: Image.Image, mask: Image.Image, rng: random.Random):
    digit_items = [i for i in rec.items if any(c.isdigit() for c in i.text)]
    if len(digit_items) < 2:
        return tamper_retype(rec, img, mask, rng)
    src, dst = rng.sample(digit_items, 2)
    sw = max(6, int((src.bbox[2] - src.bbox[0]) * rng.uniform(0.15, 0.5)))
    sx = rng.randint(src.bbox[0], max(src.bbox[0], src.bbox[2] - sw))
    patch = img.crop((sx, src.bbox[1] - 2, sx + sw, src.bbox[3] + 2))
    th = dst.bbox[3] - dst.bbox[1] + 4
    if abs(patch.height - th) > 2:
        patch = patch.resize((max(4, int(patch.width * th / patch.height)), th), Image.BICUBIC)
    dx = rng.randint(dst.bbox[0], max(dst.bbox[0], dst.bbox[2] - patch.width))
    box = (dx, dst.bbox[1] - 2, dx + patch.width, dst.bbox[1] - 2 + patch.height)
    img.paste(patch, box[:2])
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return f"copymove:{dst.field}"


def tamper_splice(rec: Receipt, img: Image.Image, mask: Image.Image, rng: random.Random):
    other = render(rng)
    if rng.random() < 0.5:
        other.image = jpeg_roundtrip(other.image, rng.randint(50, 90))
    targets = [i for i in rec.items if i.field]
    dst = rng.choice(targets)
    srcs = [i for i in other.items if i.field == dst.field] or [i for i in other.items if i.field]
    src = rng.choice(srcs)
    patch = other.image.crop(pad(src.bbox, 4, *other.image.size))
    th = dst.bbox[3] - dst.bbox[1] + 8
    patch = patch.resize((max(4, int(patch.width * th / max(1, patch.height))), th), Image.BICUBIC)
    W, H = img.size
    x = dst.bbox[0] - 4
    if dst.anchor[0] == "m":
        x = (dst.bbox[0] + dst.bbox[2]) // 2 - patch.width // 2
    elif dst.anchor[0] == "r":
        x = dst.bbox[2] + 4 - patch.width
    x = int(np.clip(x, 0, max(0, W - patch.width)))
    y = dst.bbox[1] - 4
    # cover the old text first, the way a sloppy editor would
    arr = np.asarray(img)
    ebox = pad(dst.bbox, 3, W, H)
    ImageDraw.Draw(img).rectangle(ebox, fill=border_color(arr, dst.bbox))
    img.paste(patch, (x, y))
    ImageDraw.Draw(mask).rectangle(ebox, fill=255)
    ImageDraw.Draw(mask).rectangle((x, y, x + patch.width, y + patch.height), fill=255)
    return f"splice:{dst.field}"


TAMPERS = [(tamper_retype, 0.4), (tamper_digit, 0.3), (tamper_copymove, 0.12), (tamper_splice, 0.18)]


def make_sample(seed: int, fake: bool):
    """Returns (image, mask or None, fmt, meta, encoded file bytes)."""
    rng = random.Random(seed)
    rec = render(rng)
    img = rec.image
    # the screenshot usually reached the forger already compressed once;
    # genuine screenshots get the same treatment so that alone isn't a tell
    if rng.random() < 0.55:
        img = jpeg_roundtrip(img, rng.randint(70, 96))
    mask = None
    how = "none"
    if fake:
        img = img.copy()
        mask = Image.new("L", img.size, 0)
        fn = rng.choices([t[0] for t in TAMPERS], [t[1] for t in TAMPERS])[0]
        how = fn(rec, img, mask, rng)
        if rng.random() < 0.3:  # some people edit more than one field
            how += "+" + rng.choices([t[0] for t in TAMPERS], [t[1] for t in TAMPERS])[0](rec, img, mask, rng)
    img, mask, fmt, raw = share_pipeline(img, rng, mask)
    v = rec.values
    meta = dict(seed=seed, fake=fake, tamper=how, layout=rec.layout,
                amount=v.amount, rrn=v.rrn, date=v.dt.isoformat(), vpa=v.payee_vpa)
    return img, mask, fmt, meta, raw
