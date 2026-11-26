import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowUp, Lock, MonitorSmartphone, RotateCcw, ScanLine, Smartphone, Wallet } from 'lucide-react'
import { checkHealth, checkImage, checkLink } from './api.js'
import { checkImageLocal } from './local/image.js'
import { checkLinkLocal } from './local/links.js'
import ImageInput from './components/ImageInput.jsx'
import { validateImage } from './validate.js'
import LinkInput from './components/LinkInput.jsx'
import Result from './components/Result.jsx'
import { PageProgress, Reveal } from './motion.jsx'
import { useActiveSection } from './hooks.js'
import HowItWorks from './sections/HowItWorks.jsx'
import Checks from './sections/Checks.jsx'
import SpotFake from './sections/SpotFake.jsx'
import ScoreGuide from './sections/ScoreGuide.jsx'
import About from './sections/About.jsx'
import Faq from './sections/Faq.jsx'

const LOOKS_LIKE_LINK = /^(https?:\/\/|upi:\/\/|www\.)\S+/i

const NAV = [
  ['how', 'How it works'],
  ['checks', 'What we check'],
  ['spot', 'Spot a fake'],
  ['about', 'About'],
]
// every top-level section, so the highlight clears over ones that aren't in the nav
const SECTION_IDS = ['check', 'result', 'how', 'checks', 'spot', 'score', 'about', 'faq']

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
  const [active, setActive] = useState('')

  useActiveSection(SECTION_IDS, setActive)

  useEffect(() => {
    checkHealth().then(setOnline)
  }, [])

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  const run = useCallback(async (task) => {
    const id = ++runId.current
    setStatus('loading')
    setError('')
    setResult(null)
    setProgress('')
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
      run(() => (online === false ? checkImageLocal(f, setProgress) : checkImage(f)))
    },
    [run, online],
  )

  const onLink = useCallback(
    (text) => {
      setMode('link')
      setLink(text)
      run(async () => (online === false ? checkLinkLocal(text) : checkLink(text)))
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

  // The result opens below the checker; bring it into view as soon as a check starts.
  useEffect(() => {
    if (status === 'idle') return
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
    document.getElementById('check')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const busy = status === 'loading'
  const showingResult = result && result.kind === (mode === 'image' ? 'image' : 'link')

  return (
    <div className="page">
      <a href="#check" className="skip-link">
        Skip to the checker
      </a>

      <header className="nav">
        <div className="nav-inner">
          <a href="#top" className="brand" aria-label="Receipt checker, back to top">
            <span className="brand-mark" aria-hidden="true">
              <ScanLine size={18} strokeWidth={2} />
            </span>
            <span className="brand-name">
              Receipt<span>check</span>
            </span>
          </a>
          <nav aria-label="Sections">
            <ul className="nav-links">
              {NAV.map(([id, label]) => (
                <li key={id}>
                  <a href={`#${id}`} className={active === id ? 'is-active' : undefined} aria-current={active === id ? 'true' : undefined}>
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <a href="#check" className="btn btn-primary btn-small nav-cta">
            Check a receipt
          </a>
        </div>
        <PageProgress />
      </header>

      <main id="top">
        <section id="check" className="hero" aria-labelledby="page-title">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <Reveal as="p" className="tag">
                <span className="tag-dot" aria-hidden="true" />
                Student project · UPI receipt checker
              </Reveal>
              <Reveal as="h1" id="page-title" delay={1}>
                Got paid with a screenshot? <em>Check it</em> before you hand anything over.
              </Reveal>
              <Reveal as="p" className="hero-lede" delay={2}>
                Upload a UPI or bank payment screenshot, or paste the link you were sent. You&rsquo;ll see how likely
                it is to be fake, and exactly why.
              </Reveal>
              <Reveal as="ul" className="hero-points" delay={3}>
                <li>
                  <Smartphone size={18} aria-hidden="true" />
                  Google Pay, PhonePe, Paytm, BHIM and bank receipts
                </li>
                <li>
                  <Lock size={18} aria-hidden="true" />
                  Nothing is stored or sent to anyone
                </li>
                <li>
                  <Wallet size={18} aria-hidden="true" />
                  Free to use, no sign-up
                </li>
              </Reveal>
            </div>

            <Reveal className="tool" delay={2}>
              {online === false && (
                <div className="offline" role="status">
                  <MonitorSmartphone size={18} aria-hidden="true" />
                  <p>
                    Running in your browser. Your screenshot never leaves your device. This version checks the text
                    and numbers; the pixel-edit check needs the full server.
                  </p>
                </div>
              )}
              <div className="tool-head">
                <h2 className="tool-title">Start a check</h2>
                <p className="tool-sub">Pick what you were sent</p>
              </div>

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
                  onRetry={() => file && run(() => (online === false ? checkImageLocal(file, setProgress) : checkImage(file)))}
                />
              ) : (
                <LinkInput value={link} busy={busy} onChange={setLink} onSubmit={onLink} />
              )}

              <p className="privacy">
                <Lock size={14} aria-hidden="true" />
                {online === false
                  ? 'Nothing is uploaded or stored. Nothing is sent to your bank or the payer.'
                  : 'Checked on the server and not stored. Nothing is sent to your bank or the payer.'}
              </p>
            </Reveal>
          </div>
        </section>

        <section
          id="result"
          ref={resultRef}
          className={`result-section${status === 'idle' ? ' is-empty' : ''}`}
          aria-live="polite"
          aria-busy={busy}
          aria-label="Result"
        >
          {status !== 'idle' && (
            <div className="wrap">
              <div className="result-bar">
                <h2 className="result-heading">{busy ? 'Checking' : 'Your result'}</h2>
                {!busy && (
                  <button type="button" className="btn btn-secondary" onClick={checkAnother}>
                    <RotateCcw size={16} aria-hidden="true" />
                    Check another
                  </button>
                )}
              </div>
              <div className="result-card">
                {busy && <Loading mode={mode} progress={online === false ? progress : ''} />}
                {status === 'error' && <ErrorState message={error} />}
                {status === 'done' && showingResult && <Result result={result} previewUrl={previewUrl} />}
              </div>
            </div>
          )}
        </section>

        <HowItWorks />
        <Checks />
        <SpotFake />
        <ScoreGuide />
        <About />
        <Faq />

        <section className="cta" aria-labelledby="cta-title">
          <Reveal className="wrap cta-inner">
            <h2 id="cta-title">Someone just sent you a payment screenshot?</h2>
            <p>Check it now, then open your bank app and look for the money.</p>
            <a href="#check" className="btn btn-primary">
              <ArrowUp size={18} aria-hidden="true" />
              Go to the checker
            </a>
          </Reveal>
        </section>
      </main>

      <footer className="foot">
        <div className="wrap foot-inner">
          <div>
            <p className="foot-brand">
              Receipt<span>check</span>
            </p>
            <p className="foot-note">
              A student project made for learning. The result is an estimate, not a bank confirmation. The only
              proof of payment is the money showing in your own account.
            </p>
          </div>
          <p className="foot-small">
            Not affiliated with NPCI, Google Pay, PhonePe, Paytm, BHIM or any bank. App names are used only to say
            which receipts the checker reads.
          </p>
        </div>
      </footer>
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
