import { Link2 } from 'lucide-react'

export default function LinkInput({ value, busy, onChange, onSubmit }) {
  const submit = (e) => {
    e.preventDefault()
    if (value.trim()) onSubmit(value.trim())
  }
  return (
    <form className="link-form" onSubmit={submit} noValidate>
      <label htmlFor="link" className="field-label">Link you were sent</label>
      <div className="link-field">
        <Link2 size={18} aria-hidden="true" className="link-field-icon" />
        <input
          id="link"
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck="false"
          placeholder="https://… or upi://pay?…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby="link-help"
        />
      </div>
      <p id="link-help" className="muted small">
        Paste the whole message if you like. We pick out the link and check where it really goes.
      </p>
      <button type="submit" className="btn btn-primary btn-wide" disabled={busy || !value.trim()}>
        {busy ? 'Checking…' : 'Check link'}
      </button>
    </form>
  )
}
