import { useEffect, useRef, useState } from 'react'

const TABS = [
  { id: 'original', label: 'Screenshot', help: 'Red outlines mark what looks wrong.' },
  { id: 'heat', label: 'Edited areas', help: 'Red shows where pixels look retyped or pasted in. A genuine screenshot stays grey.' },
  { id: 'ela', label: 'Error levels', help: 'Re-saving reveals compression differences. Edited text often glows brighter than the text around it.' },
]

export default function Viewer({ previewUrl, views = {}, regions = [], modelLoaded = true, isReceipt = true }) {
  const [tab, setTab] = useState('original')
  const frameRef = useRef(null)
  const available = TABS.filter((t) => t.id === 'original' ? previewUrl : views[t.id])
  const current = available.find((t) => t.id === tab) || available[0]

  // bring the first flagged area into view inside the scrollable frame
  const first = regions[0]
  const showingOriginal = current?.id === 'original'
  useEffect(() => {
    const el = frameRef.current
    if (!el || !first || !showingOriginal) return
    const img = el.querySelector('img')
    const go = () => {
      el.scrollTop = Math.max(0, first.y * img.clientHeight - el.clientHeight * 0.3)
    }
    if (img.complete) go()
    else img.addEventListener('load', go, { once: true })
  }, [first, showingOriginal])

  if (!current) return null
  const src = current.id === 'original' ? previewUrl : views[current.id]

  const onKey = (e) => {
    const i = available.findIndex((t) => t.id === current.id)
    if (e.key === 'ArrowRight') setTab(available[(i + 1) % available.length].id)
    if (e.key === 'ArrowLeft') setTab(available[(i - 1 + available.length) % available.length].id)
  }

  return (
    <section className="viewer" aria-label="Screenshot views">
      <h3 className="section-title">Look for yourself</h3>
      <div className="tabs" role="tablist" aria-label="Choose a view" onKeyDown={onKey}>
        {available.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={t.id === current.id}
            aria-controls="viewer-panel"
            tabIndex={t.id === current.id ? 0 : -1}
            className="tab"
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id="viewer-panel" role="tabpanel" aria-labelledby={`tab-${current.id}`} className="viewer-panel">
        <p className="muted small viewer-help">
          {current.id !== 'original'
            ? current.help
            : !isReceipt
              ? 'No payment details were found, so nothing in this image was checked for edits.'
              : !modelLoaded
              ? 'The edit detector isn’t loaded on this server, so nothing was marked.'
              : regions.length
                ? current.help
                : 'No line of text in this screenshot looks edited.'}
        </p>
        <div className="viewer-frame" ref={frameRef} tabIndex={0} aria-label="Screenshot preview, scrollable">
          <div className="viewer-canvas">
            <img src={src} alt={`${current.label} view of the uploaded screenshot`} />
            {current.id === 'original' &&
              regions.map((r, i) => (
                <span
                  key={i}
                  className="region"
                  style={{
                    left: `${r.x * 100}%`,
                    top: `${r.y * 100}%`,
                    width: `${r.w * 100}%`,
                    height: `${r.h * 100}%`,
                  }}
                  aria-hidden="true"
                  title={r.label}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
