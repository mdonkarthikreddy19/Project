import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CircleCheck, FileSearch, History, Lock, MonitorSmartphone, Printer, RotateCcw, ScanLine, Trash2 } from 'lucide-react'
import { checkHealth, checkImage, checkLink } from './api.js'
import { checkImageLocal } from './local/image.js'
import { checkLinkLocal } from './local/links.js'
import ImageInput from './components/ImageInput.jsx'
import { validateImage } from './validate.js'
import LinkInput from './components/LinkInput.jsx'
import Result from './components/Result.jsx'
import { SAMPLE_LINKS, sampleReceipt } from './samples.js'
import { addEntry, loadHistory, saveHistory, timeAgo } from './history.js'

const LOOKS_LIKE_LINK = /^(https?:\/\/|upi:\/\/|www\.)\S+/i

export default function App() {
  const [mode, setMode] = useState('image')
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [link, setLink] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | done | error
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const resultRef = useRef(null)
  const runId = useRef(0)
  // null while we find out; false means no server, so checks run in the browser
  const [online, setOnline] = useState(null)
  const [progress, setProgress] = useState('')
  const [history, setHistory] = useState(loadHistory)

  useEffect(() => saveHistory(history), [history])

  useEffect(() => {
    checkHealth().then(setOnline)
  }, [])

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  const run = useCallback(async (task, label) => {
    const id = ++runId.current
    setStatus('loading')
    setError('')
    setResult(null)
    setProgress('')
    try {
      const data = await task()
      if (id !== runId.current) return
      setResult(data)
      setHistory((h) =>
        addEntry(h, {
          at: Date.now(),
          kind: data.kind,
          label,
          verdict: data.verdict,
          verdictLabel: data.verdict_label,
          pct: data.fake_percent,
        }),
      )
      setStatus('done')
    } catch (err) {
      if (id !== runId.current) return
      setError(err.message)
      setStatus('error')
    }
  }, [])

  const onFile = useCallback(
    (f) => {
      const problem = validateImage(f)
      setMode('image')
      if (problem) {
        setError(problem)
        setStatus('error')
        return
      }
      setFile(f)
      setPreviewUrl(URL.createObjectURL(f))
      run(() => (online === false ? checkImageLocal(f, setProgress) : checkImage(f)), f.name)
    },
    [run, online],
  )

  const onLink = useCallback(
    (text) => {
      setMode('link')
      setLink(text)
      run(async () => (online === false ? checkLinkLocal(text) : checkLink(text)), text)
    },
    [run, online],
  )

  // Paste anywhere: an image goes to the screenshot check, a link to the link check.
  useEffect(() => {
    const onPaste = (e) => {
      const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith('image/'))
      if (item) {
        e.preventDefault()
        const blob = item.getAsFile()
        if (blob) onFile(new File([blob], 'pasted-screenshot.png', { type: blob.type }))
        return
      }
      const typing = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)
      const text = e.clipboardData?.getData('text')?.trim()
      if (!typing && text && LOOKS_LIKE_LINK.test(text)) {
        e.preventDefault()
        onLink(text)
      }
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [onFile, onLink])

  // On narrow screens the result sits under the form, so bring it into view.
  useEffect(() => {
    if (status === 'idle' || !window.matchMedia('(max-width: 959px)').matches) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    resultRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
  }, [status])

  const clear = () => {
    runId.current++
    setFile(null)
    setPreviewUrl(null)
    setResult(null)
    setError('')
    setStatus('idle')
  }

  const switchMode = (m) => {
    if (m === mode) return
    runId.current++
    setMode(m)
    setResult(null)
    setError('')
    setStatus('idle')
  }

  const checkAnother = () => {
    clear()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const busy = status === 'loading'
  const showingResult = result && result.kind === (mode === 'image' ? 'image' : 'link')

  return (
    <div className="page">
      <header className="top">
        <div className="wrap top-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <ScanLine size={18} strokeWidth={2} />
            </span>
            <div>
              <p className="brand-name">
                Receipt<span>check</span>
              </p>
              <p className="brand-sub">Fake payment receipt detection</p>
            </div>
          </div>
          <ServerStatus online={online} />
        </div>
      </header>

      <main className="wrap main">
        <div className="intro">
          <h1>Check a payment screenshot</h1>
          <p className="intro-lede">
            Upload a UPI or bank payment screenshot, or paste the link you were sent. The checker reads the receipt,
            cross-checks its details and gives the chance that it&rsquo;s fake, with the reasons.
          </p>
        </div>

        <div className="workspace">
          <div className="side">
            <section className="card tool" aria-labelledby="tool-title">
              {online === false && (
                <div className="offline" role="status">
                  <MonitorSmartphone size={18} aria-hidden="true" />
                  <p>
                    Running in your browser. Your screenshot never leaves your device. This version checks the text and
                    numbers; the pixel-edit check needs the full server.
                  </p>
                </div>
              )}
              <h2 id="tool-title" className="card-title">
                Input
              </h2>

              <div className="switch" role="tablist" aria-label="What do you want to check?">
                {[
                  ['image', 'Screenshot'],
                  ['link', 'Link'],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={mode === id}
                    className="switch-btn"
                    onClick={() => switchMode(id)}
                  >
                    {label}
                  </button>
                ))}
                <span className={`switch-thumb${mode === 'link' ? ' is-right' : ''}`} aria-hidden="true" />
              </div>

              {mode === 'image' ? (
                <ImageInput
                  file={file}
                  previewUrl={previewUrl}
                  busy={busy}
                  onFile={onFile}
                  onClear={clear}
                  onRetry={() => file && run(() => (online === false ? checkImageLocal(file, setProgress) : checkImage(file)), file.name)}
                />
              ) : (
                <LinkInput value={link} busy={busy} onChange={setLink} onSubmit={onLink} />
              )}

              <Samples
                mode={mode}
                busy={busy}
                hidden={mode === 'image' && !!file}
                onImage={async (kind) => onFile(await sampleReceipt(kind))}
                onLink={onLink}
              />

              <p className="privacy">
                <Lock size={14} aria-hidden="true" />
                {online === false
                  ? 'Nothing is uploaded or stored. Nothing is sent to your bank or the payer.'
                  : 'Checked on the server and not stored. Nothing is sent to your bank or the payer.'}
              </p>
            </section>

            {history.length > 0 && (
              <RecentChecks
                items={history}
                busy={busy}
                onLink={onLink}
                onClear={() => setHistory([])}
              />
            )}
          </div>

          <section
            className="card output"
            ref={resultRef}
            aria-live="polite"
            aria-busy={busy}
            aria-labelledby="output-title"
          >
            <div className="output-head">
              <h2 id="output-title" className="card-title">
                Result
              </h2>
              {(status === 'done' || status === 'error') && (
                <div className="output-actions">
                  {status === 'done' && (
                    <button type="button" className="btn btn-secondary" onClick={() => window.print()}>
                      <Printer size={16} aria-hidden="true" />
                      Save report
                    </button>
                  )}
                  <button type="button" className="btn btn-secondary" onClick={checkAnother}>
                    <RotateCcw size={16} aria-hidden="true" />
                    Check another
                  </button>
                </div>
              )}
            </div>
            {status === 'idle' && <Idle mode={mode} />}
            {busy && <Loading mode={mode} progress={online === false ? progress : ''} />}
            {status === 'error' && <ErrorState message={error} />}
            {status === 'done' && showingResult && <Result result={result} previewUrl={previewUrl} />}
          </section>
        </div>
      </main>
    </div>
  )
}

function ServerStatus({ online }) {
  const [label, tone, title] =
    online === null
      ? ['Connecting', 'wait', 'Looking for the checking server']
      : online
        ? ['Server online', 'on', 'Full checks, including the pixel-edit detector']
        : ['Browser mode', 'off', 'No server reached. Text and number checks run in your browser.']
  return (
    <p className={`status status-${tone}`} title={title} role="status">
      <span className="status-dot" aria-hidden="true" />
      {label}
    </p>
  )
}

function Samples({ mode, busy, hidden, onImage, onLink }) {
  if (hidden) return null
  return (
    <div className="samples">
      <p className="samples-label">{mode === 'image' ? 'No screenshot handy? Try a sample' : 'Try a sample link'}</p>
      <div className="samples-row">
        {mode === 'image' ? (
          <>
            <button type="button" className="chip" disabled={busy} onClick={() => onImage('genuine')}>
              <span className="chip-dot chip-good" aria-hidden="true" />
              Genuine receipt
            </button>
            <button type="button" className="chip" disabled={busy} onClick={() => onImage('edited')}>
              <span className="chip-dot chip-bad" aria-hidden="true" />
              Edited receipt
            </button>
          </>
        ) : (
          SAMPLE_LINKS.map(([name, url]) => (
            <button key={name} type="button" className="chip" disabled={busy} onClick={() => onLink(url)}>
              <span className="chip-dot chip-bad" aria-hidden="true" />
              {name}
            </button>
          ))
        )}
      </div>
    </div>
  )
}

const VERDICT_TONE = { genuine: 'good', unsure: 'warn', fake: 'bad', not_receipt: 'neutral' }

function RecentChecks({ items, busy, onLink, onClear }) {
  return (
    <section className="card recent" aria-labelledby="recent-title">
      <div className="recent-head">
        <h2 id="recent-title" className="card-title">
          <History size={14} aria-hidden="true" />
          Recent checks
        </h2>
        <button type="button" className="icon-btn" onClick={onClear} aria-label="Clear recent checks" title="Clear">
          <Trash2 size={16} aria-hidden="true" />
        </button>
      </div>
      <ul className="recent-list">
        {items.map((it) => {
          const body = (
            <>
              <span className={`recent-pct tone-${VERDICT_TONE[it.verdict] || 'neutral'}`}>
                {it.pct != null ? `${Math.round(it.pct)}%` : '–'}
              </span>
              <span className="recent-main">
                <span className="recent-label">{it.label}</span>
                <span className="recent-meta">
                  {it.verdictLabel} · {timeAgo(it.at)}
                </span>
              </span>
            </>
          )
          return (
            <li key={it.at}>
              {it.kind === 'link' ? (
                <button type="button" className="recent-item" disabled={busy} onClick={() => onLink(it.label)} title="Check this link again">
                  {body}
                </button>
              ) : (
                <div className="recent-item">{body}</div>
              )}
            </li>
          )
        })}
      </ul>
      <p className="recent-note">Saved in this browser only. Screenshots aren&rsquo;t kept.</p>
    </section>
  )
}

function Idle({ mode }) {
  const items =
    mode === 'image'
      ? ['A percentage for how likely the receipt is fake', 'What looks wrong and what checks out', 'Edited areas outlined on the screenshot']
      : ['A percentage for how likely the link is a scam', 'Where the link really ends up', 'What the page asks you for']
  return (
    <div className="idle">
      <span className="idle-icon" aria-hidden="true">
        <FileSearch size={26} strokeWidth={1.75} />
      </span>
      <p className="idle-title">No result yet</p>
      <p className="idle-text">
        {mode === 'image'
          ? 'Add a screenshot to start. The check takes 5 to 15 seconds.'
          : 'Paste a link to start. The check takes a few seconds.'}
      </p>
      <ul className="idle-list">
        {items.map((t) => (
          <li key={t}>
            <CircleCheck size={16} aria-hidden="true" />
            {t}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Loading({ mode, progress }) {
  const steps =
    mode === 'image'
      ? ['Reading the text on the screenshot', 'Checking the numbers and dates', 'Looking at the pixels']
      : ['Picking out the link', 'Following it to where it ends up', 'Reading what the page asks for']
  return (
    <div className="loading">
      <div className="loading-bar" aria-hidden="true">
        <span />
      </div>
      <p className="loading-title">{mode === 'image' ? 'Checking the screenshot…' : 'Checking the link…'}</p>
      <p className="loading-sub">
        {mode === 'image'
          ? progress || 'This usually takes 5 to 15 seconds.'
          : 'This takes a few seconds.'}
      </p>
      <ul className="loading-steps" aria-hidden="true">
        {steps.map((s, i) => (
          <li key={s} style={{ '--d': i }}>
            <span className="loading-dot" />
            {s}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={22} aria-hidden="true" />
      <div>
        <p className="error-title">Couldn&rsquo;t check that</p>
        <p>{message}</p>
      </div>
    </div>
  )
}
