// Browser port of backend/analysis/links.py. A browser can't open other sites for us,
// so redirects and page contents aren't checked here - only the link itself.
import { combine, finding, verdict } from './fields.js'

const OFFICIAL = {
  'Google Pay': ['pay.google.com', 'payments.google.com', 'gpay.app.goo.gl', 'g.co'],
  PhonePe: ['phonepe.com', 'phon.pe'],
  Paytm: ['paytm.com', 'paytm.me', 'paytmbank.com', 'paytmpayments.com'],
  'BHIM / NPCI': ['bhimupi.org.in', 'npci.org.in'],
  'Amazon Pay': ['amazon.in', 'amzn.in', 'amzn.to'],
  'State Bank of India': ['sbi.co.in', 'onlinesbi.sbi', 'sbi.bank.in', 'sbi'],
  'HDFC Bank': ['hdfcbank.com', 'hdfc.bank.in'],
  'ICICI Bank': ['icicibank.com', 'icici.bank.in'],
  'Axis Bank': ['axisbank.com', 'axis.bank.in'],
  'Kotak Mahindra Bank': ['kotak.com', 'kotak.bank.in'],
  'Bank of Baroda': ['bankofbaroda.in', 'bankofbaroda.bank.in'],
  'Punjab National Bank': ['pnbindia.in', 'pnb.bank.in'],
  'Canara Bank': ['canarabank.com', 'canarabank.bank.in'],
  'Union Bank of India': ['unionbankofindia.co.in', 'unionbankofindia.bank.in'],
  'IDFC FIRST Bank': ['idfcfirstbank.com', 'idfcfirst.bank.in'],
  'Yes Bank': ['yesbank.in', 'yes.bank.in'],
  'Federal Bank': ['federalbank.co.in', 'federal.bank.in'],
  Razorpay: ['razorpay.com', 'rzp.io'],
  Cashfree: ['cashfree.com'],
  'Reserve Bank of India': ['rbi.org.in'],
}
const BRAND_TOKENS = {
  phonepe: 'PhonePe', phonepay: 'PhonePe', paytm: 'Paytm', gpay: 'Google Pay', googlepay: 'Google Pay', bhim: 'BHIM / NPCI',
  npci: 'BHIM / NPCI', onlinesbi: 'State Bank of India', sbi: 'State Bank of India', hdfc: 'HDFC Bank', icici: 'ICICI Bank',
  axisbank: 'Axis Bank', kotak: 'Kotak Mahindra Bank', canara: 'Canara Bank', baroda: 'Bank of Baroda', pnb: 'Punjab National Bank',
  yesbank: 'Yes Bank', idfc: 'IDFC FIRST Bank', amazonpay: 'Amazon Pay', razorpay: 'Razorpay', upi: 'UPI',
}
const SHORTENERS = new Set(['bit.ly', 'tinyurl.com', 'cutt.ly', 'is.gd', 't.ly', 'rb.gy', 'shorturl.at', 'tiny.cc', 'ow.ly',
  's.id', 'v.gd', 'rebrand.ly', 't.co', 'goo.gl', 'bitly.com', 'short.gy', 'shrtco.de', 'u.to'])
const FREE_HOSTS = ['blogspot.', 'weebly.com', 'wixsite.com', '000webhostapp.com', 'netlify.app', 'vercel.app', 'github.io',
  'pages.dev', 'firebaseapp.com', 'web.app', 'glitch.me', 'ngrok', 'trycloudflare.com', 'sites.google.com', 'forms.gle',
  'herokuapp.com', 'onrender.com', 'replit.app', 'repl.co', 'wordpress.com', 'framer.website', 'carrd.co']
const CHEAP_TLDS = new Set(('xyz top icu click buzz live online site shop store fun monster rest cyou cfd sbs lol quest vip work ' +
  'support help info tk ml ga cf gq zip mov link space website today win bid loan').split(' '))
const BAIT = ['receipt', 'paymentsuccess', 'payment-success', 'verify', 'kyc', 'refund', 'reward', 'cashback', 'claim', 'prize',
  'lottery', 'otp', 'login', 'update', 'unlock', 'redeem', 'bonus', 'gift']
const TWO_PART = new Set(['co.in', 'org.in', 'net.in', 'gov.in', 'ac.in', 'bank.in', 'fin.in', 'firm.in', 'gen.in', 'ind.in', 'co.uk', 'com.au'])

function registrable(host) {
  const parts = host.split('.')
  for (const n of [3, 2]) {
    if (parts.length > n && TWO_PART.has(parts.slice(-n).join('.'))) return parts.slice(-(n + 1)).join('.')
  }
  return parts.length >= 2 ? parts.slice(-2).join('.') : host
}

function officialBrand(host) {
  for (const [brand, domains] of Object.entries(OFFICIAL)) {
    if (domains.some((d) => host === d || host.endsWith('.' + d))) return brand
  }
  return null
}

function editDistance(a, b) {
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i)
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]
    for (let j = 1; j <= b.length; j++) cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] !== b[j - 1])))
    prev = cur
  }
  return prev[b.length]
}

function extractUrl(text) {
  text = text.trim()
  let m = text.match(/(upi:\/\/\S+)/i)
  if (m) return m[1]
  m = text.match(/(https?:\/\/[^\s<>"']+)/i)
  if (m) return m[1].replace(/[).,;]+$/, '')
  m = text.match(/\b((?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/\S*)?)/i)
  if (m && !m[0].includes('@')) return 'https://' + m[1]
  return null
}

export function checkLinkLocal(text) {
  const url = extractUrl(text)
  if (!url) {
    const digits = text.replace(/\D/g, '')
    if ([12, 16, 22].includes(digits.length) || /^[A-Za-z]{4}[NR]\d{11,}$/.test(text.trim())) {
      throw new Error('That looks like a UTR / reference number, not a link. Open your bank or UPI app and search your transactions for it - if it isn’t there, you weren’t paid.')
    }
    throw new Error('That doesn’t look like a link. Paste the full link that was sent to you.')
  }
  const findings = []
  const details = { url }
  if (/^upi:\/\//i.test(url)) {
    const q = Object.fromEntries([...new URLSearchParams(url.split('?')[1] || '')].map(([k, v]) => [k.toLowerCase(), v]))
    Object.assign(details, { type: 'UPI payment request', pays_to: q.pa, name: q.pn, amount: q.am ? '₹' + q.am : null })
    findings.push(finding('upi_request', 'This is a payment request, not a receipt',
      'A upi:// link asks YOU to pay' + (q.am ? ` ₹${q.am}` : '') + (q.pa ? ` to ${q.pa}` : '') +
      '. It can’t prove that anyone paid you. Scammers send these as ‘click to receive money’ links.', 3.2))
    if (q.pa && !/^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/.test(q.pa)) {
      findings.push(finding('upi_bad_vpa', 'Malformed UPI ID in the link', `'${q.pa}' isn’t a valid UPI ID.`, 0.8))
    }
  } else {
    let u
    try {
      u = new URL(url)
    } catch {
      throw new Error('That link is missing a website address.')
    }
    const host = u.hostname.toLowerCase().replace(/\.$/, '')
    details.domain = host
    if (u.username) findings.push(finding('at_sign', 'Link hides its real address', `Everything before the ‘@’ is ignored by browsers. This link actually goes to ${host}.`, 1.8))
    if (u.protocol === 'http:') findings.push(finding('no_https', 'Not a secure (https) link', 'Payment apps and banks only use https.', 0.9))
    const isIp = /^\d+\.\d+\.\d+\.\d+$/.test(host) || host.startsWith('[')
    if (isIp) findings.push(finding('ip_host', 'Link points to a bare IP address', 'Real payment links use the company’s domain name, never a raw number address.', 1.8))
    if (host.startsWith('xn--') || host.includes('.xn--')) findings.push(finding('punycode', 'Address uses look-alike characters', 'The domain is written with non-English letters that can imitate a real name.', 1.8))
    const brand = officialBrand(host)
    const reg = registrable(host)
    if (brand) {
      details.brand = brand
      findings.push(finding('official', `Official ${brand} domain`, `${reg} belongs to ${brand}. That only tells you who made the link - still confirm the money in your own account.`, -1.5))
    } else if (host.endsWith('.bank.in')) {
      findings.push(finding('bank_in', 'Registered bank domain (.bank.in)', 'Only RBI-licensed banks can register .bank.in addresses.', -1.2))
    } else {
      const parts = host.split(/[.\-_]/)
      const flat = parts.join('')
      const label = reg.split('.')[0].replace(/-/g, '')
      let hit = Object.entries(BRAND_TOKENS).find(([tok]) => (tok.length > 3 && flat.includes(tok)) || (tok.length <= 3 && parts.includes(tok)))
      if (!hit) hit = Object.entries(BRAND_TOKENS).find(([tok]) => tok.length >= 5 && editDistance(label, tok) <= 2)
      if (hit) findings.push(finding('impersonation', `Pretends to be ${hit[1]}`, `The address mentions ${hit[1]} but ${reg} isn’t one of its real domains.`, 2.6))
    }
    if (SHORTENERS.has(reg) || SHORTENERS.has(host)) findings.push(finding('shortener', 'Shortened link', 'The real destination is hidden behind a link shortener.', 0.6))
    if (FREE_HOSTS.some((h) => host.includes(h))) findings.push(finding('free_host', 'Hosted on a free website builder', 'Banks and UPI apps don’t host receipts on free site builders.', 1.4))
    const tld = host.split('.').pop()
    if (CHEAP_TLDS.has(tld) && !brand) findings.push(finding('cheap_tld', `Unusual domain ending (.${tld})`, `.${tld} domains are cheap and common in scams.`, 0.8))
    const bait = BAIT.filter((w) => url.toLowerCase().includes(w))
    if (bait.length && !brand) findings.push(finding('bait_words', 'Bait words in the link', 'Contains ' + bait.slice(0, 3).map((w) => `‘${w}’`).join(', ') + '.', Math.min(1.2, 0.5 * bait.length)))
    if (!brand && !findings.some((f) => f.weight > 0.35)) {
      findings.push(finding('unknown_site', 'Not a payment app or bank website', `${reg} isn’t a known bank or UPI app domain, so the page can’t vouch for a payment.`, 0.9))
    }
  }
  const pct = combine(findings, -0.3)
  const [key, label] = verdict(pct)
  findings.sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
  return { kind: 'link', fake_percent: pct, verdict: key, verdict_label: label, findings, details, local: true }
}
