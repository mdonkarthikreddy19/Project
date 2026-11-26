import { CircleCheck } from 'lucide-react'
import { Reveal } from '../motion.jsx'

const POINTS = [
  ['Status', 'It should say the payment was successful. "Pending" or "Processing" means the money hasn’t arrived, and may never.'],
  ['Amount', 'Look at the figure closely. Retyped digits often sit slightly higher, lower or bolder than the ₹ sign next to them.'],
  ['Date and time', 'Is it today, at a time that matches when they said they paid? Old screenshots get reused.'],
  ['UTR number', 'A UPI reference is exactly 12 digits. Search your own bank app for it. If it isn’t there, you haven’t been paid.'],
  ['Name and UPI ID', 'The receiver should be you. Scammers send real receipts of payments made to someone else.'],
]

export default function SpotFake() {
  return (
    <section id="spot" className="section" aria-labelledby="spot-title">
      <div className="wrap spot-layout">
        <div className="spot-copy">
          <Reveal className="section-head section-head-left">
            <p className="kicker">Check it yourself</p>
            <h2 id="spot-title" className="section-h">Five places to look on any receipt</h2>
            <p className="section-lede">
              You don&rsquo;t need a tool for the basics. Before you hand anything over, read these five things on the
              screenshot.
            </p>
          </Reveal>
          <ol className="spot-list">
            {POINTS.map(([title, text], i) => (
              <Reveal as="li" key={title} delay={i}>
                <span className="spot-num" aria-hidden="true">
                  {i + 1}
                </span>
                <div>
                  <p className="spot-title">{title}</p>
                  <p className="spot-text">{text}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>

        <Reveal className="phone-wrap">
          <MockReceipt />
        </Reveal>
      </div>
    </section>
  )
}

// A made-up receipt drawn in HTML, with numbered markers that match the list.
function MockReceipt() {
  return (
    <figure className="phone" aria-label="Example payment receipt with the five places to check marked 1 to 5">
      <div className="phone-screen">
        <div className="mock-status">
          <span className="mock-tick">
            <CircleCheck size={30} strokeWidth={2} aria-hidden="true" />
          </span>
          <p className="mock-status-text">
            Payment successful <Pin n={1} />
          </p>
        </div>
        <p className="mock-amount">
          ₹2,450 <Pin n={2} />
        </p>
        <p className="mock-date">
          14 Nov 2026, 7:42 pm <Pin n={3} />
        </p>

        <dl className="mock-rows">
          <div>
            <dt>
              To <Pin n={5} />
            </dt>
            <dd>
              Ravi Kumar
              <span className="mock-sub">ravikumar@bank</span>
            </dd>
          </div>
          <div>
            <dt>From</dt>
            <dd>
              Ananya S.
              <span className="mock-sub">XXXXXX4821</span>
            </dd>
          </div>
          <div>
            <dt>
              UTR <Pin n={4} />
            </dt>
            <dd className="mono">431827605193</dd>
          </div>
        </dl>
        <p className="mock-foot">Example only. Not a real payment.</p>
      </div>
      <figcaption className="sr-only">
        A sample receipt showing status, amount, date, UTR number and receiver, each marked with the matching number.
      </figcaption>
    </figure>
  )
}

function Pin({ n }) {
  return (
    <span className="pin" aria-hidden="true" style={{ '--d': n }}>
      {n}
    </span>
  )
}
