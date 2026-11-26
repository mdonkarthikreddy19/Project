import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CalendarClock, FileSearch, Globe, Hash, ScanLine } from 'lucide-react'
import { checkImage, checkLink } from './api.js'
import ImageInput from './components/ImageInput.jsx'
import { validateImage } from './validate.js'
import LinkInput from './components/LinkInput.jsx'
import Result from './components/Result.jsx'

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

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  const run = useCallback(async (task) => {
    const id = ++runId.current
    setStatus('loading')
    setError('')
    setResult(null)
    try {
      const data = await task()
      if (id !== runId.current) return
      setResult(data)
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
      run(() => checkImage(f))
    },
    [run],
  )

  const onLink = useCallback(
    (text) => {
      setMode('link')
      setLink(text)
      run(() => checkLink(text))
    },
    [run],
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

  useEffect(() => {
    if ((status === 'done' || status === 'error') && window.matchMedia('(max-width: 899px)').matches) {
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
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

  const busy = status === 'loading'
  const showingResult = result && result.kind === (mode === 'image' ? 'image' : 'link')

  return (
    <div className="page">
      <header className="top">
        <div className="top-inner">
          <span className="logo-mark" aria-hidden="true">
            <ScanLine size={18} strokeWidth={2.2} />
          </span>
          <span className="top-name">Payment receipt checker</span>
        </div>
      </header>

      <main className="layout">
        <section className="panel input-panel" aria-labelledby="page-title">
          <h1 id="page-title">Is this payment real?</h1>
          <p className="lede">
            Upload a UPI or bank payment screenshot, or paste the link you were sent. You&rsquo;ll see how likely it
            is to be fake, and why.
          </p>

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
          </div>

          {mode === 'image' ? (
            <ImageInput
              file={file}
              previewUrl={previewUrl}
              busy={busy}
              onFile={onFile}
              onClear={clear}
              onRetry={() => file && run(() => checkImage(file))}
            />
          ) : (
            <LinkInput value={link} busy={busy} onChange={setLink} onSubmit={onLink} />
          )}

          <p className="privacy muted small">
            Checked on this server and not stored. Nothing is sent to your bank or the payer.
          </p>
        </section>

        <section className="panel result-panel" ref={resultRef} aria-live="polite" aria-busy={busy}>
          {busy && <Loading mode={mode} />}
          {status === 'error' && <ErrorState message={error} />}
          {status === 'done' && showingResult && <Result result={result} previewUrl={previewUrl} />}
          {status === 'idle' && <Idle mode={mode} />}
        </section>
      </main>

      <footer className="foot">
        <p>
          This is an estimate, not a bank confirmation. The only proof of payment is the money showing in your own
          account.
        </p>
      </footer>
    </div>
  )
}

function Loading({ mode }) {
  return (
    <div className="loading">
      <div className="loading-bar" aria-hidden="true">
        <span />
      </div>
      <p className="loading-title">{mode === 'image' ? 'Checking the screenshot…' : 'Checking the link…'}</p>
      <p className="muted small">
        {mode === 'image'
          ? 'Reading the text and looking at the pixels. This usually takes 5 to 15 seconds.'
          : 'Following the link to see where it really goes. This takes a few seconds.'}
      </p>
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

const IMAGE_CHECKS = [
  [Hash, 'Numbers that must agree', 'A real UTR carries the payment date inside it. So do PhonePe transaction IDs. We check them against the printed date.'],
  [CalendarClock, 'Dates and amounts', 'Impossible dates, wrong weekdays, future dates and an amount printed twice with different values.'],
  [ScanLine, 'Edited pixels', 'A model trained on edited receipts marks areas where text was retyped or pasted in.'],
  [FileSearch, 'File traces', 'Photo-editor names left in the file, and screenshots older than the payment they show.'],
]
const LINK_CHECKS = [
  [Globe, 'Where it really goes', 'Official bank and UPI app domains versus look-alikes such as phonepe-receipt.xyz.'],
  [AlertTriangle, 'Payment requests in disguise', 'A upi:// link asks you to pay. It can never prove that someone paid you.'],
  [FileSearch, 'What the page asks for', 'Pages that want your UPI PIN, OTP or card number are scams, every time.'],
]

function Idle({ mode }) {
  const rows = mode === 'image' ? IMAGE_CHECKS : LINK_CHECKS
  return (
    <div className="idle">
      <h2 className="idle-title">What we check</h2>
      <ul className="check-list">
        {rows.map(([Icon, title, text]) => (
          <li key={title}>
            <Icon size={20} className="check-icon" aria-hidden="true" />
            <div>
              <p className="check-title">{title}</p>
              <p className="muted">{text}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
