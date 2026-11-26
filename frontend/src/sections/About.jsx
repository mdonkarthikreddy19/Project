import { ArrowRight } from 'lucide-react'
import { Reveal } from '../motion.jsx'

const PIPELINE = [
  ['Screenshot', 'PNG / JPG / WebP'],
  ['OCR', 'RapidOCR reads every line'],
  ['Field checks', 'Amount, UTR, IDs, dates'],
  ['Pixel model', 'Scores each text line'],
  ['Score', '3 to 97% with reasons'],
]

const STACK = [
  ['Frontend', 'React 19, Vite, lucide icons, Tesseract.js for the in-browser mode'],
  ['Backend', 'Python, FastAPI, OpenCV, Pillow'],
  ['Text reading', 'RapidOCR (ONNX runtime, runs on CPU)'],
  ['Edit detector', 'Gradient-boosted trees in scikit-learn over 26 hand-made features per text line'],
  ['Training data', 'Receipts rendered in a script and edited on purpose: retyped digits, pasted text, copy-move'],
]

// Numbers come from models/*.json, measured on a held-out synthetic test set.
const RESULTS = [
  ['0.92', 'AUC for spotting an edited line of text', 'line model, test split'],
  ['60 / 60', 'test receipts where amount, UTR and date were all read', 'OCR + field reader'],
  ['76%', 'genuine receipts marked “looks genuine”', 'full pipeline, 100 images'],
  ['42%', 'edited receipts marked “likely fake” or “needs a look”', 'full pipeline, 100 images'],
]

export default function About() {
  return (
    <section id="about" className="section" aria-labelledby="about-title">
      <div className="wrap">
        <Reveal className="section-head section-head-left about-head">
          <p className="kicker">About the project</p>
          <h2 id="about-title" className="section-h">A student project, built to learn</h2>
          <p className="section-lede">
            Fake payment screenshots are one of the most common scams in India: a buyer &ldquo;pays&rdquo;, shows an
            edited receipt and walks away with the goods. This project was made for study, to learn how OCR, image
            forensics and machine learning can be put together to catch them. It isn&rsquo;t a commercial product
            and isn&rsquo;t connected to any bank or UPI app.
          </p>
        </Reveal>

        <Reveal className="pipeline-block">
          <h3 className="sub-h">How a screenshot moves through the system</h3>
          <ol className="pipeline">
            {PIPELINE.map(([name, text], i) => (
              <li key={name} style={{ '--d': i }}>
                <span className="pipe-step">{String(i + 1).padStart(2, '0')}</span>
                <p className="pipe-name">{name}</p>
                <p className="pipe-text">{text}</p>
                {i < PIPELINE.length - 1 && <ArrowRight className="pipe-arrow" size={18} aria-hidden="true" />}
              </li>
            ))}
          </ol>
        </Reveal>

        <div className="about-grid">
          <Reveal className="stack">
            <h3 className="sub-h">Built with</h3>
            <dl>
              {STACK.map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </Reveal>

          <Reveal className="results" delay={1}>
            <h3 className="sub-h">Test results so far</h3>
            <ul>
              {RESULTS.map(([n, label, src]) => (
                <li key={label}>
                  <p className="result-num">{n}</p>
                  <p className="result-label">{label}</p>
                  <p className="result-src">{src}</p>
                </li>
              ))}
            </ul>
            <p className="results-note">
              Measured on generated receipts, not real ones. No public set of labelled real UPI receipts exists, so
              accuracy on real screenshots is still unknown. Improving that is the next step.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
