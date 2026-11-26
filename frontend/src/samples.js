// Demo receipts drawn on a canvas, so the checker can be tried without a real screenshot.
// "edited" carries mistakes the checks look for: an impossible date, misplaced commas
// in the amount and an 11-digit UTR.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function yesterday() {
  const d = new Date(Date.now() - 86_400_000)
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, 7:42 pm`
}

export async function sampleReceipt(kind) {
  const edited = kind === 'edited'
  const c = document.createElement('canvas')
  c.width = 720
  c.height = 1280
  const x = c.getContext('2d')

  x.fillStyle = '#ffffff'
  x.fillRect(0, 0, 720, 1280)

  x.fillStyle = '#e6f4ea'
  x.beginPath()
  x.arc(360, 170, 52, 0, Math.PI * 2)
  x.fill()
  x.strokeStyle = '#15703f'
  x.lineWidth = 9
  x.lineCap = 'round'
  x.beginPath()
  x.moveTo(334, 172)
  x.lineTo(352, 190)
  x.lineTo(388, 152)
  x.stroke()

  x.textAlign = 'center'
  x.fillStyle = '#15703f'
  x.font = 'bold 40px Arial'
  x.fillText('Payment successful', 360, 290)
  x.fillStyle = '#111111'
  x.font = 'bold 90px Arial'
  x.fillText(edited ? '₹2,4500' : '₹2,450', 360, 410)
  x.fillStyle = '#555555'
  x.font = '32px Arial'
  x.fillText(edited ? '31 Feb 2026, 7:42 pm' : yesterday(), 360, 475)

  x.textAlign = 'left'
  const rows = [
    ['To', 'Ravi Kumar'],
    ['UPI ID', 'ravikumar@okaxis'],
    ['UPI transaction ID', edited ? '43182760519' : '431827605193'],
    ['From', 'Ananya S'],
  ]
  rows.forEach(([label, value], i) => {
    const y = 620 + i * 130
    x.fillStyle = '#666666'
    x.font = '32px Arial'
    x.fillText(label, 60, y)
    x.fillStyle = '#111111'
    x.font = '36px Arial'
    x.fillText(value, 60, y + 46)
    x.fillStyle = '#e5e7eb'
    x.fillRect(60, y + 76, 600, 2)
  })

  const blob = await new Promise((resolve) => c.toBlob(resolve, 'image/png'))
  return new File([blob], edited ? 'sample-edited-receipt.png' : 'sample-genuine-receipt.png', { type: 'image/png' })
}

export const SAMPLE_LINKS = [
  ['Look-alike site', 'https://phonepe-receipt.xyz/payment/success'],
  ['UPI pay request', 'upi://pay?pa=ravikumar@okaxis&pn=Refund&am=2450'],
]
