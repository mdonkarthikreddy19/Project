// Browser port of backend/analysis/fields.py - same checks, same wording, same weights.
// Lines are { text, box: [x0, y0, x1, y1] } from OCR.

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
const MON_RE = '(' + MONTHS.join('|') + ')[a-z]*'
const WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
const KNOWN_HANDLES = new Set(('okaxis oksbi okhdfcbank okicici ybl ibl axl paytm ptyes ptaxis pthdfc ptsbi upi apl yapl rapl ' +
  'abfspay axisbank axisb sbi icici hdfcbank kotak kbl fbl federal ikwik freecharge jupiteraxis naviaxis slc waicici waaxis ' +
  'wahdfcbank wasbi postbank pnb barodampay boi cnrb unionbank unionbankofindia uboi idfcbank idfcfirst idfc yesbank aubank ' +
  'rbl idbi indus indianbank iob centralbank cboi dbs equitas fino kvb mahb pingpay psb sib uco ujjivan airtel jio superyes ' +
  'sliceaxis oneyes kmbl hsbc citi sc jupiter fam bhim pty icicibank pz mbk').split(' '))
const SUCCESS = ['successful', 'success', 'completed', 'paidsuccessfully', 'moneysent', 'sentsuccessfully', 'processed',
  'paymentdone', 'transfersuccessful', 'debited', 'moneyreceived', 'received']
const PENDING = ['pending', 'processing', 'inprogress', 'awaitingconfirmation', 'underprocess']
const FAILED = ['failed', 'declined', 'unsuccessful', 'reversed', 'cancelled', 'canceled', 'rejected']
const UTR_LABELS = ['upitransactionid', 'upirefno', 'upirefid', 'upiref', 'utrno', 'utrnumber', 'utr', 'rrn',
  'bankreferenceno', 'bankrefno', 'referencenumber', 'referenceno', 'refno', 'impsrefno', 'transactionreferenceno']
const IGNORE_AMOUNT_CTX = ['cashback', 'reward', 'fee', 'charge', 'balance', 'saved', 'offer', 'won', 'limit', 'scratch', 'credit']

export const squash = (t) => t.replace(/\s+/g, '').toLowerCase()
const height = (l) => l.box[3] - l.box[1]
const sameRow = (a, b) => Math.min(a.box[3], b.box[3]) - Math.max(a.box[1], b.box[1]) > 0.5 * Math.min(height(a), height(b))

export function finding(code, title, detail, weight) {
  const kind = weight >= 0.35 ? 'bad' : weight <= -0.35 ? 'good' : 'note'
  return { code, title, detail, weight, kind }
}

function digitish(s) {
  const letters = [...s].filter((c) => /[a-z]/i.test(c)).length
  const digits = [...s].filter((c) => /\d/.test(c)).length
  if (s.length >= 8 && letters <= 2 && digits / s.length >= 0.75) {
    return s.replace(/[oO]/g, '0').replace(/[lIi]/g, '1').replace(/[sS]/g, '5')
  }
  return s
}

const fmtDate = (d) => d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
const fmtDateTime = (d) =>
  `${fmtDate(d)}, ${d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })}`

// ---------------------------------------------------------------- dates

function year(y) {
  const n = parseInt(y, 10)
  return n < 100 ? n + 2000 : n
}

function findDate(text) {
  text = text.replace(/0ct/g, 'oct').replace(/n0v/g, 'nov').replace(/0ec/g, 'dec')
  const pats = [
    [new RegExp(`(?<!\\d)(\\d{1,2})(?:st|nd|rd|th)?[\\s,\\-.']*${MON_RE}[\\s,\\-.']*(\\d{4}|\\d{2}(?!\\d))`), 'dmy'],
    [new RegExp(`${MON_RE}[\\s.\\-]*(\\d{1,2})(?:st|nd|rd|th)?[\\s,]*(\\d{4})`), 'mdy'],
    [/(\d{4})-(\d{2})-(\d{2})/, 'iso'],
    [/(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2}(?!\d))/, 'num'],
  ]
  for (const [re, kind] of pats) {
    const m = text.match(re)
    if (!m) continue
    const g = m.slice(1)
    const s = m.index
    const e = m.index + m[0].length
    if (kind === 'dmy') return [parseInt(g[0], 10), MONTHS.indexOf(g[1]) + 1, year(g[2]), s, e, text]
    if (kind === 'mdy') return [parseInt(g[1], 10), MONTHS.indexOf(g[0]) + 1, year(g[2]), s, e, text]
    if (kind === 'iso') return [parseInt(g[2], 10), parseInt(g[1], 10), parseInt(g[0], 10), s, e, text]
    let d = parseInt(g[0], 10)
    let mo = parseInt(g[1], 10)
    if (mo > 12 && d <= 12) [d, mo] = [mo, d]
    return [d, mo, year(g[2]), s, e, text]
  }
  return null
}

function findTime(text) {
  const m = text.match(/(?<!\d)(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?/)
  if (!m) return null
  let h = parseInt(m[1], 10)
  const mi = parseInt(m[2], 10)
  const sec = m[3] ? parseInt(m[3], 10) : null
  const ap = (m[4] || '').replace(/\./g, '')
  if (ap === 'pm' && h < 12) h += 12
  if (ap === 'am' && h === 12) h = 0
  return [h, mi, sec]
}

function validDate(y, mo, d) {
  const dt = new Date(y, mo - 1, d)
  return dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d
}

function parseWhen(lines, imgH, out) {
  const topCut = imgH * 0.045
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i]
    const t = squash(ln.text)
    const found = findDate(t)
    if (!found || ln.box[3] < topCut) continue
    const [d, mo, y, s, e, norm] = found
    out.whenText = ln.text
    out.boxes.date = ln.box
    let tm = findTime(norm.slice(e)) || findTime(norm.slice(0, s))
    if (!tm) {
      for (const j of [i - 1, i + 1]) {
        if (j >= 0 && j < lines.length && lines[j].box[3] > topCut && !findDate(squash(lines[j].text))) {
          tm = findTime(squash(lines[j].text))
          if (tm) break
        }
      }
    }
    if (!validDate(y, mo, d)) {
      out.findings.push(finding('date_invalid', 'The date doesn’t exist',
        `The receipt shows day ${d} of month ${mo}, ${y}. No app would print an impossible date, so this was almost certainly typed in.`, 3.0))
      return
    }
    if (tm && (tm[0] > 23 || tm[1] > 59 || (tm[2] != null && tm[2] > 59))) {
      out.findings.push(finding('time_invalid', 'The time isn’t a real time', `The receipt shows ${tm[0]}:${String(tm[1]).padStart(2, '0')}.`, 2.5))
      return
    }
    out.when = tm ? new Date(y, mo - 1, d, tm[0], tm[1], tm[2] || 0) : new Date(y, mo - 1, d)
    out.hasTime = !!tm
    const wd = norm.slice(0, s).match(/(?<![a-z])(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?[,|\s]*$/)
    const base = new Date(y, mo - 1, d)
    const pyWeekday = (base.getDay() + 6) % 7
    if (wd && WEEKDAYS.indexOf(wd[1]) !== pyWeekday) {
      out.findings.push(finding('weekday', 'Weekday doesn’t match the date',
        `It says ${wd[1][0].toUpperCase() + wd[1].slice(1)}, but ${fmtDate(base)} was a ${base.toLocaleDateString('en-GB', { weekday: 'long' })}.`, 2.5))
    }
    if (out.when.getTime() > Date.now() + 86400000) {
      out.findings.push(finding('future', 'Date is in the future', `The receipt is dated ${fmtDate(out.when)}, which hasn’t happened yet.`, 3.0))
    }
    return
  }
}

// ---------------------------------------------------------------- references

function parseRefs(lines, out) {
  let labelled = null
  for (let i = 0; i < lines.length && !labelled; i++) {
    const t = squash(lines[i].text)
    for (const lab of UTR_LABELS) {
      const k = t.indexOf(lab)
      if (k < 0) continue
      let rest = t.slice(k + lab.length).replace(/^[:.\-#]+/, '')
      let src = lines[i]
      if (rest.length < 6) {
        const nxt = lines[i + 1]
        if (nxt) {
          rest = squash(nxt.text).replace(/^[:.\-#]+/, '')
          src = nxt
        } else rest = ''
      }
      let val = digitish(rest.replace(/[^0-9a-z]/g, ''))
      const num = val.match(/\d{12}/)
      if (num) val = num[0]
      if (val.length >= 6) labelled = [val, src]
      break
    }
  }
  const twelve = []
  for (const ln of lines) {
    const t = digitish(squash(ln.text).replace(/[^0-9a-z]/g, ' '))
    for (const m of t.matchAll(/(?<![0-9a-z])\d{12}(?![0-9a-z])/g)) twelve.push([m[0], ln])
  }
  if (labelled) {
    out.utr = /^\d+$/.test(labelled[0]) ? labelled[0] : labelled[0].toUpperCase()
    out.boxes.utr = labelled[1].box
  } else if (twelve.length) {
    out.utr = twelve[0][0]
    out.boxes.utr = twelve[0][1].box
  }
  for (const ln of lines) {
    const t = digitish(squash(ln.text))
    const m = t.match(/(?<![a-z0-9])t(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{4,14})(?!\d)/)
    if (m) {
      out.txnId = 'T' + m[0].slice(1)
      out.boxes.txn_id = ln.box
      out.tid = m
      break
    }
    const g = squash(ln.text).match(/cicag[a-z0-9_-]{6,}/)
    if (g && !out.txnId) {
      const orig = ln.text.replace(/\s/g, '').match(/CICAg[\w-]+/i)
      out.txnId = orig ? orig[0] : g[0]
      out.boxes.txn_id = ln.box
    }
  }
}

function checkRefs(out) {
  const f = out.findings
  const u = out.utr
  if (!u) {
    if (out.txnId) {
      f.push(finding('no_utr', 'No UTR shown', 'There’s an app transaction ID but no UTR. Cashback and wallet credits look like this.', 0.1))
      return
    }
    if (['Google Pay', 'PhonePe', 'Paytm', 'UPI app'].includes(out.app)) {
      f.push(finding('no_utr', 'No UTR / reference number found',
        'Every completed UPI payment has a 12-digit UTR. Screenshots that crop it out, or never had one, deserve suspicion.', 1.0))
    } else if (out.app.startsWith('Bank')) {
      f.push(finding('no_utr', 'No reference number found', 'Bank transfer receipts normally show a UTR or reference number.', 0.8))
    }
    return
  }
  const neft = u.toLowerCase().match(/^([a-z]{4})n(\d)(\d{3})(\d{5,})$/)
  const rtgs = u.toLowerCase().match(/^([a-z]{4})r(\d{4})(\d{2})(\d{2})(\d{5,})$/)
  if (neft || rtgs) {
    if (!out.when) return
    let ok
    let what
    if (neft) {
      const jd = dayOfYear(out.when)
      ok = parseInt(neft[2], 10) === out.when.getFullYear() % 10 && Math.abs(parseInt(neft[3], 10) - jd) <= 2
      what = `year …${neft[2]}, day ${neft[3]}`
    } else {
      const d = new Date(+rtgs[2], +rtgs[3] - 1, +rtgs[4])
      ok = Math.abs(d - new Date(out.when.getFullYear(), out.when.getMonth(), out.when.getDate())) <= 2 * 86400000
      what = fmtDate(d)
    }
    f.push(ok
      ? finding('bank_utr_match', 'UTR matches the transfer date', `The UTR encodes ${what}, consistent with the receipt.`, -0.6)
      : finding('bank_utr_mismatch', 'UTR doesn’t match the transfer date', `The UTR encodes ${what} but the receipt is dated ${fmtDate(out.when)}.`, 1.0))
    return
  }
  if (!/^\d+$/.test(u)) {
    if (out.app !== 'Bank transfer') f.push(finding('utr_letters', 'UTR contains letters', `The UTR reads '${u}'. UPI UTRs are digits only.`, 0.9))
    return
  }
  if (u.length !== 12) {
    f.push(finding('utr_length', 'UTR is the wrong length', `'${u}' has ${u.length} digits. A UPI UTR always has exactly 12.`, 2.4))
    return
  }
  f.push(finding('utr_ok', 'UTR has the right format', '12 digits, like every UPI reference number.', -0.2))
}

function dayOfYear(d) {
  return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(d.getFullYear(), 0, 0)) / 86400000)
}

function checkTxnId(out) {
  const m = out.tid
  if (!m || !out.when) return
  const [yy, mo, dd, hh, mi, ss] = m.slice(1, 7).map((x) => parseInt(x, 10))
  const stamp = new Date(2000 + yy, mo - 1, dd, hh, mi, ss)
  if (!validDate(2000 + yy, mo, dd) || hh > 23 || mi > 59 || ss > 59) {
    out.findings.push(finding('tid_invalid', 'Transaction ID has an impossible timestamp',
      `${out.txnId} should start with T + date + time, but the date in it doesn’t exist.`, 1.8))
    return
  }
  const diff = Math.abs(stamp - out.when) / 1000
  const sameDay = stamp.toDateString() === out.when.toDateString()
  const hm = (d) => d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (diff <= 180 || (!out.hasTime && sameDay)) {
    out.findings.push(finding('tid_match', 'Transaction ID matches the time',
      `The ID is stamped ${fmtDate(stamp)} ${stamp.toLocaleTimeString('en-GB')}, same as the receipt.`, -0.6))
  } else if (sameDay) {
    out.findings.push(finding('tid_time', 'Transaction ID time is off', `The ID is stamped ${hm(stamp)}, the receipt says ${hm(out.when)}.`, 1.0))
  } else {
    out.findings.push(finding('tid_mismatch', 'Transaction ID doesn’t match the date',
      `The ID is stamped ${fmtDate(stamp)} but the receipt says ${fmtDate(out.when)}.`, 1.6))
  }
}

// ---------------------------------------------------------------- amount

const AMOUNT_NUM = '([0-9][0-9,]*(?:\\.[0-9]{1,2})?)'
const CURRENCY = '(?:₹|天|rs\\.?|inr|(?<![a-z0-9])z(?=\\d)|(?<=of)[?&](?=\\d))'
const amountValue = (s) => {
  const v = parseFloat(s.replace(/,/g, ''))
  return Number.isFinite(v) ? v : null
}

function parseAmount(lines, imgH, out) {
  const cands = []
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i]
    if (ln.box[3] < imgH * 0.045) continue
    const low = squash(ln.text)
    for (const m of low.matchAll(new RegExp(CURRENCY + ':?' + AMOUNT_NUM, 'g'))) cands.push([m[1], ln, true])
    const tot = low.match(/(?:total|amount)[^0-9a-z]{0,3}[a-z#]?[^0-9a-z]{0,2}([0-9][0-9,]*\.[0-9]{2})/)
    if (tot && !cands.some((c) => c[1] === ln)) cands.push([tot[1], ln, true])
    const bare = low.match(/^[₹天z%?&]?([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{2})?|[0-9]{1,6}(?:\.[0-9]{2})?)$/)
    if (bare && !cands.some((c) => c[1] === ln)) cands.push([bare[1], ln, ['₹', '天', '?', '&'].includes(low[0])])
    if (low.includes('amount')) {
      for (let j = i + 1; j < Math.min(i + 3, lines.length); j++) {
        const mj = squash(lines[j].text).match(new RegExp('^[₹天z%?&]?(?:rs\\.?|inr)?' + AMOUNT_NUM + '$'))
        if (mj && (sameRow(ln, lines[j]) || j === i + 1)) {
          cands.push([mj[1], lines[j], true])
          break
        }
      }
    }
  }
  const ok = cands.filter(([t]) => amountValue(t) != null && t.replace(/,/g, '').split('.')[0].length <= 9)
  if (!ok.length) return
  const tagged = ok.filter((c) => c[2])
  let main
  if (tagged.length) {
    const key = (c) => [['total', 'amount', 'paid', 'debited'].some((w) => squash(c[1].text).includes(w)) ? 1 : 0, height(c[1]), -c[1].box[1]]
    main = tagged.reduce((a, b) => (cmp(key(b), key(a)) > 0 ? b : a))
  } else {
    const shaped = ok.filter((c) => c[0].includes(',') || /\.\d\d$/.test(c[0]))
    if (shaped.length) main = shaped.reduce((a, b) => (height(b[1]) > height(a[1]) ? b : a))
    else {
      const hs = lines.map(height).sort((a, b) => a - b)
      const median = hs[Math.floor(hs.length / 2)]
      main = ok.reduce((a, b) => (height(b[1]) > height(a[1]) ? b : a))
      if (height(main[1]) < median * 1.6) return
    }
  }
  out.amountValue = amountValue(main[0])
  out.amount = '₹' + main[0]
  out.boxes.amount = main[1].box
  const intPart = main[0].split('.')[0]
  if (intPart.includes(',') && !/^\d{1,2}(,\d{2})*,\d{3}$/.test(intPart) && !/^\d{1,3}(,\d{3})+$/.test(intPart)) {
    out.findings.push(finding('amount_commas', 'Commas in the amount are in the wrong places',
      `'${main[0]}' isn’t how any payment app groups digits. Commas usually shift when a digit is added or removed by hand.`, 1.6))
  }
  if (main[0].includes('.') && main[0].split('.')[1].length === 1) {
    out.findings.push(finding('amount_decimals', 'Amount has one decimal digit', `'${main[0]}' - apps always print paise with two digits.`, 0.9))
  }
  const other = tagged.find(([t, ln]) => ln !== main[1] && amountValue(t) !== out.amountValue &&
    !IGNORE_AMOUNT_CTX.some((w) => squash(ln.text).includes(w)))
  if (other) {
    out.findings.push(finding('amount_conflict', 'The amount appears twice with different values',
      `Headline says ₹${main[0]} but elsewhere it says ₹${other[0]}. Edits often change one copy and miss the other.`, 2.2))
  }
}

function cmp(a, b) {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i]
  return 0
}

// ---------------------------------------------------------------- the rest

function parseMisc(lines, out) {
  const text = lines.map((l) => squash(l.text)).join(' ')
  if (/googletransactionid|googlepay|gpay/.test(text)) out.app = 'Google Pay'
  else if (text.includes('phonepe') || (text.includes('transferdetails') && /t\d{20}/.test(text))) out.app = 'PhonePe'
  else if (text.includes('paytm') || (text.includes('upirefno') && text.includes('orderid'))) out.app = 'Paytm'
  else if (text.includes('bhim')) out.app = 'BHIM'
  else if (text.includes('amazonpay')) out.app = 'Amazon Pay'
  else if (/neft|rtgs|imps|beneficiary|fundstransfer|ifsc/.test(text)) out.app = 'Bank transfer'
  else if (text.includes('upi') && /transactionid|paidto|utr|upiid|upiref|sentto|debitedfrom|paymentsuccessful|moneysent/.test(text)) out.app = 'UPI app'
  else if (text.includes('upi')) out.app = 'Paid by UPI (printed)'

  for (const [words, status] of [[FAILED, 'Failed'], [PENDING, 'Pending'], [SUCCESS, 'Successful']]) {
    const hit = lines.find((ln) => words.some((w) => squash(ln.text).includes(w)))
    if (hit) {
      out.status = status
      out.boxes.status = hit.box
      break
    }
  }
  if (out.status === 'Failed' || out.status === 'Pending') {
    out.findings.push(finding('status_' + out.status.toLowerCase(), `Receipt itself says ${out.status.toLowerCase()}`,
      'This screen does not show a completed payment. Don’t release goods against it.', 1.8))
  }
  // "@ptyes on Paytm" squashes to "@ptyesonpaytm": drop the "on <app>" tail
  const m = text.match(/([a-z0-9][a-z0-9.\-_]{1,})@([a-z]{2,}?)(?:on(?:paytm|googlepay|phonepe|gpay|bhim))?(?![a-z])/)
  if (m && !['gmail', 'yahoo', 'outlook', 'hotmail', 'rediffmail'].includes(m[2])) {
    out.vpa = `${m[1]}@${m[2]}`
    const ln = lines.find((l) => squash(l.text).includes(out.vpa))
    if (ln) out.boxes.vpa = ln.box
    if (!KNOWN_HANDLES.has(m[2]) && !['ok', 'pt', 'wa'].some((p) => m[2].startsWith(p))) {
      out.findings.push(finding('vpa_handle', 'Unfamiliar UPI handle',
        `'@${m[2]}' isn’t one of the common bank/app handles. It may be a newer bank, or a typo made while editing.`, 0.3))
    }
  }
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i]
    const mt = ln.text.match(/^(?:paid\s*to|sent\s*to|to)[:\s]*([A-Za-z][A-Za-z .&'-]{2,})$/i)
    if (mt && !ln.text.includes('@')) {
      out.payee = mt[1].trim()
      out.boxes.payee = ln.box
      break
    }
    const sq = squash(ln.text)
    if (['paidto', 'sentto', 'to', 'beneficiaryname'].includes(sq) && lines[i + 1]) {
      const nxt = lines[i + 1]
      const words = sq === 'to' ? 2 : 1
      if (/^[A-Za-z][A-Za-z .&'-]{2,}$/.test(nxt.text) && nxt.text.split(/\s+/).length >= words) {
        out.payee = nxt.text.trim()
        out.boxes.payee = nxt.box
        break
      }
    }
  }
}

export function analyseText(lines, imgH) {
  const out = { app: 'Unknown', status: null, amount: null, amountValue: null, when: null, whenText: null, utr: null,
    txnId: null, payee: null, vpa: null, hasTime: false, tid: null, boxes: {}, findings: [], isReceipt: false }
  if (!lines.length) return out
  lines.sort((a, b) => Math.round(a.box[1] / 12) - Math.round(b.box[1] / 12) || a.box[0] - b.box[0])
  parseMisc(lines, out)
  parseWhen(lines, imgH, out)
  parseAmount(lines, imgH, out)
  parseRefs(lines, out)
  const signals = [out.amount, out.utr || out.txnId, out.status, out.when, out.vpa, out.app !== 'Unknown'].filter(Boolean).length
  out.isReceipt = signals >= 3
  if (out.isReceipt) {
    checkRefs(out)
    checkTxnId(out)
    if (out.when && out.when < Date.now() - 2 * 365 * 86400000) {
      out.findings.push(finding('old', 'Payment is over two years old', `Dated ${fmtDate(out.when)}. Old receipts get reused as proof of new payments.`, 0.4))
    }
  }
  out.summary = {
    app: out.app,
    status: out.status,
    amount: out.amount,
    date: out.when ? fmtDateTime(out.when) : out.whenText,
    utr: out.utr,
    transaction_id: out.txnId,
    paid_to: out.payee,
    upi_id: out.vpa,
  }
  return out
}

export function combine(findings, prior = 0) {
  const z = prior + findings.reduce((s, f) => s + f.weight, 0)
  const p = 1 / (1 + Math.exp(-z))
  return Math.round(Math.min(97, Math.max(3, p * 100)) * 10) / 10
}

export function verdict(pct) {
  if (pct >= 65) return ['fake', 'Likely fake or edited']
  if (pct >= 35) return ['unsure', 'Needs a closer look']
  return ['genuine', 'Looks genuine']
}
