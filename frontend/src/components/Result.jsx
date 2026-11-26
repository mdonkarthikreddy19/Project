import { useEffect, useState } from 'react'
import { CircleCheck, CircleX, Copy, Info, ShieldAlert, ShieldCheck, ShieldX, ScanSearch, Check } from 'lucide-react'
import Viewer from './Viewer.jsx'

const VERDICTS = {
  genuine: {
    Icon: ShieldCheck,
    tone: 'good',
    line: 'Nothing we checked looks edited or out of place.',
  },
  unsure: {
    Icon: ShieldAlert,
    tone: 'warn',
    line: 'Some things don’t add up. Don’t rely on this screenshot alone.',
  },
  fake: {
    Icon: ShieldX,
    tone: 'bad',
    line: 'Don’t hand over goods or money based on this.',
  },
  not_receipt: {
    Icon: ScanSearch,
    tone: 'neutral',
    line: 'We couldn’t find an amount, reference number and status together. Upload the full payment confirmation screen, not a crop or a chat.',
  },
}

const DETAIL_LABELS = [
  ['app', 'Sent from'],
  ['status', 'Status'],
  ['amount', 'Amount'],
  ['date', 'Date and time'],
  ['utr', 'UTR / reference'],
  ['transaction_id', 'Transaction ID'],
  ['paid_to', 'Paid to'],
  ['upi_id', 'UPI ID'],
  ['type', 'Link type'],
  ['pays_to', 'Pays money to'],
  ['name', 'Name in link'],
  ['domain', 'Website'],
  ['final_domain', 'Ends up on'],
  ['title', 'Page title'],
]
const MONO = new Set(['utr', 'transaction_id', 'upi_id', 'pays_to', 'domain', 'final_domain'])

export default function Result({ result, previewUrl }) {
  const v = VERDICTS[result.verdict] || VERDICTS.unsure
  const pct = result.fake_percent
  const findings = result.findings || []
  const bad = findings.filter((f) => f.kind === 'bad')
  const good = findings.filter((f) => f.kind === 'good')
  const notes = findings.filter((f) => f.kind === 'note')
  const details = { ...(result.details || {}) }
  if (details.app === 'Unknown') delete details.app

  const image = result.kind === 'image'

  return (
    <div className={`result${image ? ' has-side' : ''}`}>
      <div className="result-main">
        <section className={`verdict tone-${v.tone}`} aria-labelledby="verdict-title">
          <div className="verdict-head">
            <v.Icon className="verdict-icon" size={28} strokeWidth={2} aria-hidden="true" />
            <h3 id="verdict-title" className="verdict-title">{result.verdict_label}</h3>
          </div>
          {pct != null && <Score pct={pct} />}
          <p className="verdict-line">{v.line}</p>
          <NextStep result={result} details={details} />
        </section>

        {bad.length > 0 && <FindingList title={result.verdict === 'not_receipt' ? 'Also noticed' : 'What looks wrong'} items={bad} />}
        {good.length > 0 && <FindingList title="What checks out" items={good} />}
        {notes.length > 0 && <FindingList title="Notes" items={notes} />}

        <DetailTable details={details} redirects={details.redirects} flagged={flaggedRows(result)} receipt={image && result.is_receipt} />

        {image && result.file && <FileLine file={result.file} seconds={result.seconds} model={result.model_loaded} />}
      </div>

      {image && (
        <div className="result-side">
          <Viewer previewUrl={previewUrl} views={result.views} regions={result.regions} modelLoaded={result.model_loaded} isReceipt={result.is_receipt} local={!!result.local} />
        </div>
      )}
    </div>
  )
}

function Score({ pct }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1100
    let frame
    const start = performance.now()
    const tick = (now) => {
      const t = duration ? Math.min(1, (now - start) / duration) : 1
      setShown(pct * (1 - Math.pow(1 - t, 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [pct])
  return (
    <div className="score">
      <p className="score-number">
        <span className="score-value">{Math.round(shown)}%</span>
        <span className="score-label">chance it&rsquo;s fake</span>
      </p>
      <div
        className="meter"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        aria-label="Chance the payment proof is fake"
      >
        <div className="meter-fill" style={{ transform: `scaleX(${shown / 100})` }} />
        <span className="meter-tick" style={{ left: '35%' }} aria-hidden="true" />
        <span className="meter-tick" style={{ left: '65%' }} aria-hidden="true" />
      </div>
      <div className="meter-scale" aria-hidden="true">
        <span>Looks genuine</span>
        <span>Needs a look</span>
        <span>Likely fake</span>
      </div>
    </div>
  )
}

function NextStep({ result, details }) {
  let text
  if (result.kind === 'link' && details.type === 'UPI payment request') {
    text = 'Don\u2019t open this link in a UPI app and never enter your PIN. Receiving money never needs your PIN.'
  } else if (result.kind === 'image' && details.utr) {
    text = (
      <>
        Open your bank or UPI app and look for {details.amount ? <>a credit of <strong>{details.amount}</strong> with </> : ''}UTR{' '}
        <span className="mono">{details.utr}</span>. If it isn&rsquo;t there, you haven&rsquo;t been paid.
      </>
    )
  } else if (result.verdict === 'not_receipt') {
    return null
  } else {
    text = 'Check that the money shows up in your own bank or UPI app before you hand anything over.'
  }
  return (
    <p className="next-step">
      <strong>Next: </strong>
      {text}
    </p>
  )
}

// fields named by failed checks, mapped to rows of "What we read"
const FIELD_TO_ROW = { amount: 'amount', utr: 'utr', date: 'date', txn_id: 'transaction_id', status: 'status', vpa: 'upi_id', payee: 'paid_to' }
function flaggedRows(result) {
  return new Set((result.flagged_fields || []).map((f) => FIELD_TO_ROW[f]).filter(Boolean))
}

function FindingList({ title, items }) {
  return (
    <section className="findings" aria-label={title}>
      <h4 className="section-title">{title}</h4>
      <ul>
        {items.map((f) => (
          <li key={f.code} className={`finding finding-${f.kind}`}>
            {f.kind === 'bad' && <CircleX className="finding-icon" size={20} aria-label="Problem" />}
            {f.kind === 'good' && <CircleCheck className="finding-icon" size={20} aria-label="Passed" />}
            {f.kind === 'note' && <Info className="finding-icon" size={20} aria-label="Note" />}
            <div>
              <p className="finding-title">{f.title}</p>
              <p className="finding-detail">{f.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function DetailTable({ details, redirects, flagged, receipt }) {
  const rows = DETAIL_LABELS.filter(([k]) => details[k] || (k === 'amount' && receipt))
  if (!rows.length) return null
  return (
    <section aria-label="What we read">
      <h4 className="section-title">What we read</h4>
      <dl className="details">
        {rows.map(([k, label]) => (
          <div className={`details-row${flagged.has(k) ? ' is-flagged' : ''}`} key={k}>
            <dt>{label}</dt>
            <dd className={MONO.has(k) && details[k] ? 'mono' : undefined}>
              {details[k] || <span className="muted">Couldn&rsquo;t read it</span>}
              {k === 'utr' && details[k] && <CopyButton text={details[k]} />}
              {flagged.has(k) && (
                <span className="row-flag">
                  <CircleX size={16} aria-hidden="true" />
                  Doesn&rsquo;t add up
                </span>
              )}
            </dd>
          </div>
        ))}
        {redirects?.length > 0 && (
          <div className="details-row">
            <dt>Redirects</dt>
            <dd className="mono redirects">
              {redirects.map((r) => (
                <span key={r}>{r}</span>
              ))}
            </dd>
          </div>
        )}
      </dl>
    </section>
  )
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setDone(true)
      setTimeout(() => setDone(false), 1600)
    } catch {
      // clipboard blocked (http on a phone); the number is selectable anyway
    }
  }
  return (
    <button type="button" className="icon-btn copy-btn" onClick={copy} aria-label={done ? 'Copied' : 'Copy UTR'}>
      {done ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
    </button>
  )
}

function FileLine({ file, seconds, model }) {
  const parts = [file.format, file.width && `${file.width} × ${file.height}`]
  if (file.jpeg_quality) parts.push(`JPEG quality ~${file.jpeg_quality}`)
  if (file.software) parts.push(`saved by ${file.software}`)
  if (file.camera) parts.push(`camera: ${file.camera}`)
  return (
    <p className="file-line muted small">
      {parts.filter(Boolean).join(' · ')}
      {seconds != null && ` · checked in ${seconds}s`}
      {!model && ' · edit detector not loaded, pixel check skipped'}
    </p>
  )
}
