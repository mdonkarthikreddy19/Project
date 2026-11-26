import { ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react'
import { Reveal } from '../motion.jsx'

const BANDS = [
  {
    Icon: ShieldCheck,
    tone: 'good',
    range: '3 to 35%',
    title: 'Looks genuine',
    text: 'Nothing we checked looks edited or out of place. Still confirm the money in your own account.',
  },
  {
    Icon: ShieldAlert,
    tone: 'warn',
    range: '35 to 65%',
    title: 'Needs a look',
    text: 'Some things don’t add up. Read the reasons and don’t rely on the screenshot alone.',
  },
  {
    Icon: ShieldX,
    tone: 'bad',
    range: '65 to 97%',
    title: 'Likely fake',
    text: 'Several checks failed. Don’t hand over goods or money based on this.',
  },
]

export default function ScoreGuide() {
  return (
    <section id="score" className="section section-tint" aria-labelledby="score-title">
      <div className="wrap">
        <Reveal className="section-head">
          <p className="kicker">Reading the result</p>
          <h2 id="score-title" className="section-h">What the percentage means</h2>
          <p className="section-lede">
            Each check adds or removes a bit of evidence. The total becomes a percentage. It never goes below 3% or
            above 97%, because a screenshot alone can never prove a payment either way.
          </p>
        </Reveal>

        <Reveal className="guide-meter" aria-hidden="true">
          <div className="guide-track">
            <span className="guide-marker">
              <span>72%</span>
            </span>
          </div>
          <div className="guide-scale">
            <span>0</span>
            <span style={{ left: '35%' }}>35</span>
            <span style={{ left: '65%' }}>65</span>
            <span>100</span>
          </div>
        </Reveal>

        <ul className="bands">
          {BANDS.map(({ Icon, tone, range, title, text }, i) => (
            <Reveal as="li" className={`band tone-${tone}`} key={title} delay={i}>
              <div className="band-head">
                <Icon size={22} strokeWidth={2} aria-hidden="true" />
                <p className="band-title">{title}</p>
              </div>
              <p className="band-range">{range}</p>
              <p className="band-text">{text}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  )
}
