import { Reveal } from '../motion.jsx'

const QUESTIONS = [
  [
    'Can this confirm that I was paid?',
    'No. Only your own bank or UPI app can do that. This checker catches the mistakes edited receipts usually make, which is useful when you can’t check your account straight away.',
  ],
  [
    'Is my screenshot saved anywhere?',
    'No. With the server, the image is checked and not stored. In browser mode it never leaves your device at all.',
  ],
  [
    'Which apps does it work with?',
    'Google Pay, PhonePe, Paytm, BHIM and bank transfer receipts (IMPS, NEFT, RTGS). Upload the full confirmation screen, not a crop or a chat bubble.',
  ],
  [
    'It said "looks genuine". Can I trust it?',
    'Treat it as a good sign, not proof. A real receipt for a payment made to someone else will pass every check. Make sure the receiver name and UPI ID are yours.',
  ],
  [
    'Why did a real receipt get flagged?',
    'Heavy compression, screenshots of screenshots and photos of a screen can look edited. Try the original screenshot from the sender’s phone.',
  ],
  [
    'Someone sent me a link to "receive" money.',
    'Receiving money never needs your UPI PIN. A upi://pay link or a page asking for your PIN or OTP is asking you to pay, not to receive.',
  ],
]

export default function Faq() {
  return (
    <section id="faq" className="section section-tint" aria-labelledby="faq-title">
      <div className="wrap faq-layout">
        <Reveal className="faq-head">
          <p className="kicker">Questions</p>
          <h2 id="faq-title" className="section-h">Things people ask</h2>
        </Reveal>
        <dl className="faq">
          {QUESTIONS.map(([q, a], i) => (
            <Reveal key={q} className="faq-item" delay={i % 2}>
              <dt>{q}</dt>
              <dd>{a}</dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  )
}
