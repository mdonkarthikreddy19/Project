import { useRef, useState } from 'react'
import { ImageUp, RotateCcw, X } from 'lucide-react'
import { ACCEPT } from '../validate.js'

export default function ImageInput({ file, previewUrl, busy, onFile, onClear, onRetry }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const pick = () => inputRef.current?.click()

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) onFile(f)
  }

  if (file && previewUrl) {
    return (
      <div className="picked">
        <div className="picked-thumb">
          <img src={previewUrl} alt="The screenshot you chose" />
        </div>
        <div className="picked-meta">
          <p className="picked-name" title={file.name}>{file.name}</p>
          <p className="muted small">{formatBytes(file.size)}</p>
          <div className="picked-actions">
            <button type="button" className="btn btn-secondary" onClick={pick} disabled={busy}>
              <ImageUp size={18} aria-hidden="true" />
              Choose another
            </button>
            <button type="button" className="btn btn-secondary" onClick={onRetry} disabled={busy}>
              <RotateCcw size={18} aria-hidden="true" />
              Check again
            </button>
          </div>
        </div>
        <button type="button" className="icon-btn picked-clear" onClick={onClear} disabled={busy} aria-label="Remove screenshot">
          <X size={18} aria-hidden="true" />
        </button>
        <input ref={inputRef} type="file" accept={ACCEPT} hidden onChange={(e) => e.target.files[0] && onFile(e.target.files[0])} />
      </div>
    )
  }

  return (
    <div
      className={`dropzone${dragging ? ' is-dragging' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <ImageUp className="dropzone-icon" size={32} strokeWidth={2} aria-hidden="true" />
      <p className="dropzone-title">Add the payment screenshot</p>
      <p className="muted small">Google Pay, PhonePe, Paytm, BHIM or a bank transfer receipt</p>
      <button type="button" className="btn btn-primary btn-wide" onClick={pick} disabled={busy}>
        Choose screenshot
      </button>
      <p className="muted small dropzone-hint">
        <span className="only-pointer">or drag it here, or paste with Ctrl+V</span>
        <span className="only-touch">JPG, PNG or WebP, up to 12 MB</span>
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          if (e.target.files[0]) onFile(e.target.files[0])
          e.target.value = ''
        }}
      />
    </div>
  )
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
