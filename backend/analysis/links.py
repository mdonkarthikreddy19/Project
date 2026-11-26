"""
Checks a link someone sent as "proof" of payment.

There's no public API that confirms a UPI payment from a link, so this judges
where the link really goes: official app/bank domain or a lookalike, a UPI
*payment request* disguised as a receipt, shorteners, free hosting, and
pages that ask for a PIN, OTP or password.
"""
from __future__ import annotations

import html as html_lib
import ipaddress
import re
import socket
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from .findings import Finding

OFFICIAL = {
    "Google Pay": ["pay.google.com", "payments.google.com", "gpay.app.goo.gl", "g.co"],
    "PhonePe": ["phonepe.com", "phon.pe"],
    "Paytm": ["paytm.com", "paytm.me", "paytmbank.com", "paytmpayments.com"],
    "BHIM / NPCI": ["bhimupi.org.in", "npci.org.in"],
    "Amazon Pay": ["amazon.in", "amzn.in", "amzn.to"],
    "State Bank of India": ["sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "onlinesbi.sbi.bank.in", "sbi"],
    "HDFC Bank": ["hdfcbank.com", "hdfc.bank.in"],
    "ICICI Bank": ["icicibank.com", "icici.bank.in"],
    "Axis Bank": ["axisbank.com", "axis.bank.in"],
    "Kotak Mahindra Bank": ["kotak.com", "kotak.bank.in"],
    "Bank of Baroda": ["bankofbaroda.in", "bankofbaroda.bank.in"],
    "Punjab National Bank": ["pnbindia.in", "pnb.bank.in"],
    "Canara Bank": ["canarabank.com", "canarabank.bank.in"],
    "Union Bank of India": ["unionbankofindia.co.in", "unionbankofindia.bank.in"],
    "IDFC FIRST Bank": ["idfcfirstbank.com", "idfcfirst.bank.in"],
    "Yes Bank": ["yesbank.in", "yes.bank.in"],
    "Federal Bank": ["federalbank.co.in", "federal.bank.in"],
    "Razorpay": ["razorpay.com", "rzp.io"],
    "Cashfree": ["cashfree.com"],
    "Reserve Bank of India": ["rbi.org.in"],
}
BRAND_TOKENS = {
    "phonepe": "PhonePe", "phonepay": "PhonePe", "paytm": "Paytm", "gpay": "Google Pay", "googlepay": "Google Pay",
    "bhim": "BHIM / NPCI", "npci": "BHIM / NPCI", "onlinesbi": "State Bank of India", "sbi": "State Bank of India",
    "hdfc": "HDFC Bank", "icici": "ICICI Bank", "axisbank": "Axis Bank", "kotak": "Kotak Mahindra Bank",
    "canara": "Canara Bank", "baroda": "Bank of Baroda", "pnb": "Punjab National Bank", "yesbank": "Yes Bank",
    "idfc": "IDFC FIRST Bank", "amazonpay": "Amazon Pay", "razorpay": "Razorpay", "upi": "UPI",
}
SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.ly", "rb.gy", "shorturl.at", "tiny.cc", "ow.ly",
              "s.id", "v.gd", "rebrand.ly", "t.co", "goo.gl", "bitly.com", "short.gy", "shrtco.de", "u.to"}
FREE_HOSTS = ["blogspot.", "weebly.com", "wixsite.com", "000webhostapp.com", "netlify.app", "vercel.app",
              "github.io", "pages.dev", "firebaseapp.com", "web.app", "glitch.me", "ngrok", "trycloudflare.com",
              "sites.google.com", "forms.gle", "herokuapp.com", "onrender.com", "replit.app", "repl.co",
              "wordpress.com", "framer.website", "carrd.co", "godaddysites.com", "mystrikingly.com"]
CHEAP_TLDS = {"xyz", "top", "icu", "click", "buzz", "live", "online", "site", "shop", "store", "fun", "monster",
              "rest", "cyou", "cfd", "sbs", "lol", "quest", "vip", "work", "support", "help", "info", "tk", "ml",
              "ga", "cf", "gq", "zip", "mov", "link", "space", "website", "today", "win", "bid", "loan"}
BAIT_WORDS = ["receipt", "paymentsuccess", "payment-success", "verify", "kyc", "refund", "reward", "cashback",
              "claim", "prize", "lottery", "otp", "login", "update", "unlock", "redeem", "bonus", "gift"]
TWO_PART_SUFFIX = {"co.in", "org.in", "net.in", "gov.in", "ac.in", "bank.in", "fin.in", "firm.in", "gen.in",
                   "ind.in", "co.uk", "com.au"}


def registrable(host: str) -> str:
    parts = host.split(".")
    for n in (3, 2):
        if len(parts) > n and ".".join(parts[-n:]) in TWO_PART_SUFFIX:
            return ".".join(parts[-(n + 1):])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def official_brand(host: str) -> str | None:
    for brand, domains in OFFICIAL.items():
        for d in domains:
            if host == d or host.endswith("." + d):
                return brand
    return None


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def extract_url(text: str) -> str | None:
    text = text.strip()
    m = re.search(r"(upi://[^\s]+)", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(https?://[^\s<>\"']+)", text, re.I)
    if m:
        return m.group(1).rstrip(").,;")
    m = re.search(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)", text, re.I)
    if m and "@" not in m.group(0):
        return "https://" + m.group(1)
    return None


# ------------------------------------------------------------------ upi:// intents

def check_upi_intent(url: str):
    q = {k.lower(): v[0] for k, v in parse_qs(urlparse(url).query).items()}
    details = {"type": "UPI payment request", "pays_to": q.get("pa"), "name": q.get("pn"),
               "amount": ("₹" + q["am"]) if q.get("am") else None, "note": q.get("tn")}
    f = [Finding("upi_request", "This is a payment request, not a receipt",
                 "A upi:// link asks YOU to pay" + (f" {details['amount']}" if details["amount"] else "") +
                 (f" to {q.get('pa')}" if q.get("pa") else "") +
                 ". It can't prove that anyone paid you. Scammers send these as 'click to receive money' links.", 3.2)]
    if q.get("pa") and not re.fullmatch(r"[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}", q["pa"]):
        f.append(Finding("upi_bad_vpa", "Malformed UPI ID in the link", f"'{q['pa']}' isn't a valid UPI ID.", 0.8))
    return f, details


# ------------------------------------------------------------------ fetching (with SSRF guard)

def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise PermissionError("internal address")
    return True


def fetch(url: str, max_hops=5, max_bytes=300_000):
    chain = [url]
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Mobile Safari/537.36"}
    for _ in range(max_hops + 1):
        host = urlparse(url).hostname or ""
        if not _public_host(host):
            return {"chain": chain, "error": "dns"}
        r = requests.get(url, headers=headers, timeout=6, allow_redirects=False, stream=True)
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            nxt = r.headers.get("location")
            r.close()
            if not nxt:
                break
            url = urljoin(url, nxt)
            chain.append(url)
            if url.lower().startswith("upi://"):
                return {"chain": chain, "upi": url}
            continue
        body = b""
        for chunk in r.iter_content(16384):
            body += chunk
            if len(body) >= max_bytes:
                break
        r.close()
        return {"chain": chain, "status": r.status_code, "html": body.decode(r.encoding or "utf-8", errors="ignore"),
                "ctype": r.headers.get("content-type", "")}
    return {"chain": chain, "error": "too_many_redirects"}


def page_findings(page: dict, brand: str | None) -> tuple[list[Finding], dict]:
    f, d = [], {}
    html = page.get("html", "")
    low = html.lower()
    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if t:
        d["title"] = re.sub(r"\s+", " ", unquote(t.group(1))).strip()[:140]
    if re.search(r"<input[^>]+type=[\"']?password", low) or re.search(r"upi\s*pin|enter\s*(your\s*)?pin|\bmpin\b", low):
        f.append(Finding("asks_pin", "Page asks for a PIN or password",
                         "You never need to enter your UPI PIN, password or OTP to receive money. This is how money gets stolen.", 3.0))
    elif re.search(r"\botp\b|one[\s-]?time\s*password|\bcvv\b|card\s*number|expiry", low):
        f.append(Finding("asks_otp", "Page asks for OTP or card details",
                         "Receiving money never requires an OTP or card number.", 2.4))
    if brand is None and re.search(r"payment\s*(successful|received|success)|transaction\s*successful|money\s*received", low):
        f.append(Finding("fake_success_page", "Shows a 'payment successful' page on an unofficial site",
                         "Anyone can build a web page that says 'payment received'. Only your own bank or UPI app can confirm it.", 1.4))
    return f, d


# ------------------------------------------------------------------ main entry

def analyse_link(text: str, do_fetch: bool = True):
    url = extract_url(text)
    if not url:
        digits = re.sub(r"\D", "", text)
        if len(digits) in (12, 16, 22) or re.fullmatch(r"[A-Za-z]{4}[NR]\d{11,}", text.strip()):
            return None, "That looks like a UTR / reference number, not a link. Open your bank or UPI app and search your transactions for it - if it isn't there, you weren't paid."
        return None, "That doesn't look like a link. Paste the full link that was sent to you."

    findings: list[Finding] = []
    details: dict = {"url": url}

    if url.lower().startswith("upi://"):
        f, d = check_upi_intent(url)
        details.update(d)
        return (findings + f, details), None

    p = urlparse(url)
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return None, "That link is missing a website address."
    details["domain"] = host
    if "@" in p.netloc:
        findings.append(Finding("at_sign", "Link hides its real address",
                                f"Everything before the '@' is ignored by browsers. This link actually goes to {host}.", 1.8))
    if p.scheme == "http":
        findings.append(Finding("no_https", "Not a secure (https) link", "Payment apps and banks only use https.", 0.9))
    try:
        ipaddress.ip_address(host)
        findings.append(Finding("ip_host", "Link points to a bare IP address",
                                "Real payment links use the company's domain name, never a raw number address.", 1.8))
    except ValueError:
        pass
    if host.startswith("xn--") or ".xn--" in host:
        findings.append(Finding("punycode", "Address uses look-alike characters",
                                "The domain is written with non-English letters that can imitate a real name.", 1.8))

    brand = official_brand(host)
    reg = registrable(host)
    if brand:
        details["brand"] = brand
        findings.append(Finding("official", f"Official {brand} domain",
                                f"{reg} belongs to {brand}. That only tells you who made the link - still confirm the money in your own account.", -1.5))
    elif host.endswith(".bank.in"):
        findings.append(Finding("bank_in", "Registered bank domain (.bank.in)",
                                "Only RBI-licensed banks can register .bank.in addresses.", -1.2))
    else:
        label = reg.split(".")[0].replace("-", "")
        parts = re.split(r"[.\-_]", host)
        flat = "".join(parts)
        # short tokens (sbi, upi, pnb) only count as a whole word, otherwise "groupie" looks like UPI
        hit = next((b for tok, b in BRAND_TOKENS.items()
                    if (len(tok) > 3 and tok in flat) or (len(tok) <= 3 and tok in parts)), None)
        if hit is None:
            hit = next((b for tok, b in BRAND_TOKENS.items() if len(tok) >= 5 and edit_distance(label, tok) <= 2), None)
        if hit:
            findings.append(Finding("impersonation", f"Pretends to be {hit}",
                                    f"The address mentions {hit} but {reg} isn't one of its real domains.", 2.6))

    if reg in SHORTENERS or host in SHORTENERS:
        findings.append(Finding("shortener", "Shortened link", "The real destination is hidden behind a link shortener.", 0.6))
    if any(h in host for h in FREE_HOSTS):
        findings.append(Finding("free_host", "Hosted on a free website builder",
                                "Banks and UPI apps don't host receipts on free site builders.", 1.4))
    tld = host.rsplit(".", 1)[-1]
    if tld in CHEAP_TLDS and not brand:
        findings.append(Finding("cheap_tld", f"Unusual domain ending (.{tld})", f".{tld} domains are cheap and common in scams.", 0.8))
    bait = [w for w in BAIT_WORDS if w in url.lower()]
    if bait and not brand:
        findings.append(Finding("bait_words", "Bait words in the link",
                                "Contains " + ", ".join(f"'{w}'" for w in bait[:3]) + ".", min(1.2, 0.5 * len(bait))))

    if do_fetch and not any(f.code == "ip_host" for f in findings):
        try:
            page = fetch(url)
            details["redirects"] = page["chain"][1:]
            if page.get("upi"):
                f, d = check_upi_intent(page["upi"])
                findings += f
                details.update(d)
            elif page.get("error") == "dns":
                findings.append(Finding("no_dns", "Website doesn't exist",
                                        f"{host} doesn't resolve. Fake receipt sites are often taken down quickly.", 0.8))
            elif page.get("html") is not None:
                final_host = (urlparse(page["chain"][-1]).hostname or "").lower()
                if final_host != host:
                    details["final_domain"] = final_host
                    fb = official_brand(final_host)
                    if brand and not fb:
                        findings.append(Finding("redirect_away", "Redirects away from the official site",
                                                f"Starts on {host} but ends on {final_host}.", 1.6))
                    brand = brand or fb
                f, d = page_findings(page, brand)
                findings += f
                details.update(d)
        except PermissionError:
            findings.append(Finding("internal", "Link points to a private network address", "Refused to open it.", 1.5))
        except requests.exceptions.SSLError:
            findings.append(Finding("bad_tls", "Broken security certificate",
                                    "The site's https certificate is invalid. Real payment sites never have this.", 1.4))
        except requests.RequestException:
            details["fetch_error"] = "Could not open the page"

    if not brand and not any(f.weight > 0.35 for f in findings):
        findings.append(Finding("unknown_site", "Not a payment app or bank website",
                                f"{reg} isn't a known bank or UPI app domain, so the page can't vouch for a payment.", 0.9))
    return (findings, details), None
