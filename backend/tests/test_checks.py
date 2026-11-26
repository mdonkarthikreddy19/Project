"""
Fast checks for the text rules and link rules - no OCR, no network.

    python -m pytest backend/tests        (or: python backend/tests/test_checks.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.fields import analyse_text  # noqa: E402
from analysis.findings import combine  # noqa: E402
from analysis.links import analyse_link, edit_distance, registrable  # noqa: E402
from analysis.ocr import Line  # noqa: E402


def lines(*rows):
    """Fake OCR output: (text, height) rows stacked top to bottom on a 1000px-tall screen."""
    out, y = [], 100
    for text, h in rows:
        out.append(Line(text, (40, y, 600, y + h), 0.99))
        y += h + 20
    return out


def codes(parsed):
    return {f.code for f in parsed.findings}


GENUINE = [
    ("Transaction Successful", 24),
    ("10:42 am on 26 Nov 2026", 16),
    ("Paid to", 16),
    ("Rahul Sharma", 20),
    ("rahul99@ybl", 16),
    ("₹1,250", 40),
    ("Transaction ID", 16),
    ("T2611261042318812345678", 18),
    ("UTR: 633010123456", 17),
]


def test_genuine_receipt_passes():
    p = analyse_text(lines(*GENUINE), 1000)
    assert p.is_receipt
    assert p.amount == "₹1,250"
    assert p.utr == "633010123456"
    assert {"utr_ok", "tid_match"} <= codes(p)
    assert combine(p.findings, prior=-0.3) < 35


def test_real_utrs_are_not_flagged():
    # real UTRs from the user's own Google Pay / PhonePe / Paytm screenshots
    for utr in ("669601348390", "252700316474", "669060686635", "319364546998"):
        rows = [r if not r[0].startswith("UTR") else (f"UTR: {utr}", 17) for r in GENUINE]
        p = analyse_text(lines(*rows), 1000)
        assert not [f for f in p.findings if f.kind == "bad"], utr


def test_google_transaction_id_with_dash():
    rows = GENUINE + [("Google transaction ID", 16), ("CICAgPjj-Y6TYg", 18)]
    p = analyse_text(lines(*[r for r in rows if not r[0].startswith("T26")]), 1000)
    assert p.txn_id == "CICAgPjj-Y6TYg"


def test_wrong_length_utr():
    rows = [r if not r[0].startswith("UTR") else ("UTR: 63301012345", 17) for r in GENUINE]
    assert "utr_length" in codes(analyse_text(lines(*rows), 1000))


def test_impossible_date():
    rows = [r if "Nov" not in r[0] else ("10:42 am on 31 Feb 2026", 16) for r in GENUINE]
    assert "date_invalid" in codes(analyse_text(lines(*rows), 1000))


def test_wrong_weekday():
    rows = [r if "Nov" not in r[0] else ("Mon, 26 Nov 2026 | 10:42 am", 16) for r in GENUINE]
    assert "weekday" in codes(analyse_text(lines(*rows), 1000))


def test_pm_on_is_not_a_weekday():
    # "pm on" squashes to "pmon" - that must not read as Monday
    rows = [r if "Nov" not in r[0] else ("10:42 pm on 26 Nov 2026", 16) for r in GENUINE]
    assert "weekday" not in codes(analyse_text(lines(*rows), 1000))


def test_amount_conflict():
    rows = GENUINE + [("Debited from XXXX1234   ₹12,500", 16)]
    assert "amount_conflict" in codes(analyse_text(lines(*rows), 1000))


def test_bad_comma_grouping():
    rows = [r if not r[0].startswith("₹") else ("₹1,2500", 40) for r in GENUINE]
    assert "amount_commas" in codes(analyse_text(lines(*rows), 1000))


def test_pending_status():
    rows = [r if r[0] != "Transaction Successful" else ("Payment Pending", 24) for r in GENUINE]
    assert "status_pending" in codes(analyse_text(lines(*rows), 1000))


def test_ocr_rupee_variants():
    rows = [r if not r[0].startswith("₹") else ("天1,250", 40) for r in GENUINE]
    assert analyse_text(lines(*rows), 1000).amount == "₹1,250"


def test_ocr_rupee_amount_wins_over_smaller_numbers():
    # PhonePe-style: amount only slightly bigger than body text, rupee sign read as 天
    rows = [r if not r[0].startswith("₹") else ("天1,649.15", 23) for r in GENUINE]
    assert analyse_text(lines(*rows), 1000).amount == "₹1,649.15"


def test_chat_text_is_not_a_receipt():
    p = analyse_text(lines(("hey did you send it?", 16), ("yes bro check", 16), ("ok", 16)), 1000)
    assert not p.is_receipt


def test_upi_intent_link():
    (findings, details), err = analyse_link("upi://pay?pa=x@ybl&pn=Refund&am=500", do_fetch=False)
    assert err is None
    assert any(f.code == "upi_request" for f in findings)
    assert details["amount"] == "₹500"


def test_lookalike_domains():
    for url in ("https://phonepe-receipt.xyz/t/1", "https://paytrn.in/r", "https://gpay-verify.online"):
        (findings, _), _ = analyse_link(url, do_fetch=False)
        assert any(f.code == "impersonation" for f in findings), url


def test_official_domains():
    for url in ("https://www.phonepe.com/", "https://sbi.bank.in", "https://paytm.com/x"):
        (findings, _), _ = analyse_link(url, do_fetch=False)
        assert any(f.code == "official" for f in findings), url
        assert combine(findings, prior=-0.3) < 35


def test_short_tokens_need_whole_words():
    (findings, _), _ = analyse_link("https://groupie-tracker.com", do_fetch=False)
    assert not any(f.code == "impersonation" for f in findings)


def test_utr_text_is_not_a_link():
    res, err = analyse_link("633010123456", do_fetch=False)
    assert res is None and "UTR" in err


def test_helpers():
    assert registrable("onlinesbi.sbi.bank.in") == "sbi.bank.in"
    assert registrable("pay.google.com") == "google.com"
    assert edit_distance("paytm", "paytrn") == 2


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, e)
    sys.exit(1 if failed else 0)
