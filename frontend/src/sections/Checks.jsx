import { AlertTriangle, CalendarClock, FileSearch, Globe, Hash, ScanLine, BadgeIndianRupee, CircleDashed, Link2Off, KeyRound } from 'lucide-react'
import { Reveal } from '../motion.jsx'

const IMAGE_CHECKS = [
  [Hash, 'Numbers that must agree', 'Every UPI UTR has exactly 12 digits. PhonePe transaction IDs carry the exact payment time, so we compare them with the time printed on the receipt.'],
  [CalendarClock, 'Dates that make sense', 'Impossible dates like 31 February, a weekday that doesn’t match the date, and payments dated in the future.'],
  [BadgeIndianRupee, 'The amount', 'The same amount printed twice with different values, or commas in places the Indian number format never puts them.'],
  [CircleDashed, 'Payment status', 'Pending and failed payments cropped or passed off as successful ones.'],
  [ScanLine, 'Edited lines of text', 'A model trained on edited receipts scores every line of text against its neighbours: background, noise, sharp seams and ink colour.'],
  [FileSearch, 'Traces in the file', 'Photo-editor names left inside the file, and screenshots saved before the payment they claim to show.'],
]

const LINK_CHECKS = [
  [Globe, 'Where it really goes', 'Official bank and UPI app domains versus look-alikes such as phonepe-receipt.xyz. Redirects are followed to the final page.'],
  [AlertTriangle, 'Payment requests in disguise', 'A upi:// link asks you to pay. It can never prove that someone paid you.'],
  [Link2Off, 'Throwaway hosting', 'Link shorteners, free website builders and cheap domain endings that scam pages favour.'],
  [KeyRound, 'What the page asks for', 'Pages that want your UPI PIN, OTP or card number are scams, every time.'],
]

export default function Checks() {
  return (
    <section id="checks" className="section section-tint" aria-labelledby="checks-title">
      <div className="wrap checks-layout">
        <Reveal className="checks-intro">
          <p className="kicker">What we check</p>
          <h2 id="checks-title" className="section-h">The details fakes usually get wrong</h2>
          <p className="section-lede">
            Editing apps make it easy to change a name or an amount. Keeping every number, date and pixel consistent
            afterwards is much harder. That&rsquo;s what these checks look for.
          </p>
          <p className="checks-count">
            <strong>{IMAGE_CHECKS.length}</strong> screenshot checks
            <span aria-hidden="true"> · </span>
            <strong>{LINK_CHECKS.length}</strong> link checks
          </p>
        </Reveal>

        <div className="checks-groups">
          <CheckGroup title="On a screenshot" rows={IMAGE_CHECKS} />
          <CheckGroup title="On a link" rows={LINK_CHECKS} />
        </div>
      </div>
    </section>
  )
}

function CheckGroup({ title, rows }) {
  return (
    <div className="check-group">
      <Reveal as="h3" className="check-group-title">
        {title}
      </Reveal>
      <ul className="check-grid">
        {rows.map(([Icon, name, text], i) => (
          <Reveal as="li" className="check-card" key={name} delay={i % 2}>
            <span className="check-icon" aria-hidden="true">
              <Icon size={20} strokeWidth={2} />
            </span>
            <p className="check-name">{name}</p>
            <p className="check-text">{text}</p>
          </Reveal>
        ))}
      </ul>
    </div>
  )
}
