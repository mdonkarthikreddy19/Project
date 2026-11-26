import { ClipboardPaste, ListChecks, Gauge } from 'lucide-react'
import { Reveal } from '../motion.jsx'
import { useScrollProgress } from '../hooks.js'

const STEPS = [
  {
    Icon: ClipboardPaste,
    title: 'Add the screenshot or link',
    text: 'Choose the payment screenshot someone sent you, drag it in, or paste it with Ctrl+V. For a link, paste the whole message; we pick the link out of it.',
    note: 'JPG, PNG or WebP, up to 12 MB',
  },
  {
    Icon: ListChecks,
    title: 'We read it and cross-check it',
    text: 'The text is read with OCR. Then the amount, UTR, transaction ID, date and status are checked against each other, and the pixels are checked for retyped or pasted-in lines.',
    note: 'Usually 5 to 15 seconds',
  },
  {
    Icon: Gauge,
    title: 'You get a score and the reasons',
    text: 'A percentage for how likely the proof is fake, a list of what looks wrong and what checks out, and the screenshot with suspicious areas outlined.',
    note: 'Then confirm in your own bank app',
  },
]

export default function HowItWorks() {
  const lineRef = useScrollProgress()
  return (
    <section id="how" className="section" aria-labelledby="how-title">
      <div className="wrap">
        <Reveal className="section-head">
          <p className="kicker">How it works</p>
          <h2 id="how-title" className="section-h">Three steps, about ten seconds</h2>
          <p className="section-lede">No sign-up and nothing to install. The page does the reading and checking for you.</p>
        </Reveal>

        <ol className="steps" ref={lineRef}>
          <span className="steps-line" aria-hidden="true">
            <span />
          </span>
          {STEPS.map(({ Icon, title, text, note }, i) => (
            <Reveal as="li" className="step" key={title} delay={i}>
              <span className="step-num" aria-hidden="true">
                {i + 1}
              </span>
              <div className="step-body">
                <div className="step-title-row">
                  <Icon size={20} strokeWidth={2} aria-hidden="true" />
                  <h3 className="step-title">{title}</h3>
                </div>
                <p className="step-text">{text}</p>
                <p className="step-note">{note}</p>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  )
}
