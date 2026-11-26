// In-browser screenshot check: Tesseract OCR + the same text rules as the server.
// Used when the Python checker isn't reachable (e.g. the GitHub Pages copy of the site).
import { analyseText, combine, finding, verdict } from './fields.js'

let workerPromise = null

function getWorker() {
  if (!workerPromise) {
    workerPromise = import('tesseract.js').then(({ createWorker }) => createWorker('eng'))
  }
  return workerPromise
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => resolve({ img, url })
    img.onerror = () => reject(new Error('Couldn’t open that file as an image. Try a JPG or PNG screenshot.'))
    img.src = url
  })
}

// Tesseract reads dark text on light backgrounds best: invert dark-mode screenshots, upscale small ones.
function prepare(img) {
  const scale = img.naturalWidth < 1000 ? 2 : 1
  const c = document.createElement('canvas')
  c.width = img.naturalWidth * scale
  c.height = img.naturalHeight * scale
  const ctx = c.getContext('2d', { willReadFrequently: true })
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(img, 0, 0, c.width, c.height)
  const data = ctx.getImageData(0, 0, c.width, c.height)
  const px = data.data
  let sum = 0
  for (let i = 0; i < px.length; i += 16) sum += 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]
  const dark = sum / (px.length / 16) < 110
  for (let i = 0; i < px.length; i += 4) {
    let g = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]
    if (dark) g = 255 - g
    px[i] = px[i + 1] = px[i + 2] = g
  }
  ctx.putImageData(data, 0, 0)
  return { canvas: c, scale }
}

function elaView(img) {
  return new Promise((resolve) => {
    const w = Math.min(720, img.naturalWidth)
    const h = Math.round((img.naturalHeight * w) / img.naturalWidth)
    const a = document.createElement('canvas')
    a.width = w
    a.height = h
    const actx = a.getContext('2d', { willReadFrequently: true })
    actx.drawImage(img, 0, 0, w, h)
    const orig = actx.getImageData(0, 0, w, h)
    const re = new Image()
    re.onload = () => {
      actx.drawImage(re, 0, 0)
      const comp = actx.getImageData(0, 0, w, h)
      const diff = new Float32Array(w * h)
      let max = 8
      for (let i = 0, j = 0; i < orig.data.length; i += 4, j++) {
        const d = Math.max(Math.abs(orig.data[i] - comp.data[i]), Math.abs(orig.data[i + 1] - comp.data[i + 1]), Math.abs(orig.data[i + 2] - comp.data[i + 2]))
        diff[j] = d
        if (d > max) max = d
      }
      const out = actx.createImageData(w, h)
      const k = 255 / Math.min(max, 40)
      for (let j = 0; j < diff.length; j++) {
        const v = Math.min(255, diff[j] * k)
        out.data[j * 4] = out.data[j * 4 + 1] = out.data[j * 4 + 2] = v
        out.data[j * 4 + 3] = 255
      }
      actx.putImageData(out, 0, 0)
      resolve(a.toDataURL('image/jpeg', 0.85))
    }
    re.src = a.toDataURL('image/jpeg', 0.9)
  })
}

function collectLines(data, scale) {
  const lines = []
  for (const block of data.blocks || []) {
    for (const para of block.paragraphs || []) {
      for (const ln of para.lines || []) {
        const text = (ln.text || '').trim()
        if (!text || ln.confidence < 30) continue
        const b = ln.bbox
        lines.push({ text, box: [b.x0 / scale, b.y0 / scale, b.x1 / scale, b.y1 / scale] })
      }
    }
  }
  return lines
}

const FIELD_OF = { date_invalid: 'date', time_invalid: 'date', weekday: 'date', future: 'date', old: 'date', vpa_handle: 'vpa' }
const FIELD_PREFIX = [['utr_', 'utr'], ['bank_utr', 'utr'], ['tid_', 'txn_id'], ['amount_', 'amount'], ['status_', 'status']]

export async function checkImageLocal(file, onProgress) {
  const t0 = performance.now()
  const { img, url } = await loadImage(file)
  try {
    onProgress?.('Loading the text reader (first time only)…')
    const worker = await getWorker()
    onProgress?.('Reading the text…')
    const { canvas, scale } = prepare(img)
    const { data } = await worker.recognize(canvas, {}, { blocks: true })
    const lines = collectLines(data, scale)
    const parsed = analyseText(lines, img.naturalHeight)
    const findings = [...parsed.findings]
    findings.push(finding('browser_mode', 'Pixel check not run', 'This quick check ran in your browser and only checked the text and numbers. The full checker also looks for edited pixels.', 0))

    const W = img.naturalWidth
    const H = img.naturalHeight
    const regions = []
    const flagged = []
    for (const f of findings) {
      const key = FIELD_OF[f.code] || FIELD_PREFIX.find(([p]) => f.code.startsWith(p))?.[1]
      if (f.kind === 'bad' && key && parsed.boxes[key] && !flagged.includes(key)) {
        flagged.push(key)
        const [x0, y0, x1, y1] = parsed.boxes[key]
        regions.push({ x: Math.max(0, x0 - 6) / W, y: Math.max(0, y0 - 6) / H, w: (x1 - x0 + 12) / W, h: (y1 - y0 + 12) / H, label: f.title, field: key })
      }
    }
    const result = {
      kind: 'image',
      local: true,
      is_receipt: parsed.isReceipt,
      details: parsed.summary,
      flagged_fields: flagged,
      regions,
      views: { ela: await elaView(img) },
      model_loaded: true,
      file: { format: (file.type.split('/')[1] || 'image').toUpperCase(), width: W, height: H },
    }
    if (!parsed.isReceipt) {
      Object.assign(result, { fake_percent: null, verdict: 'not_receipt', verdict_label: 'This doesn’t look like a payment receipt', findings: findings.filter((f) => f.kind === 'bad') })
    } else {
      // no line model here, so start a little further toward genuine to keep the same verdict bands
      const pct = combine(findings, -0.8)
      const [key, label] = verdict(pct)
      findings.sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
      Object.assign(result, { fake_percent: pct, verdict: key, verdict_label: label, findings })
    }
    result.seconds = Math.round((performance.now() - t0) / 10) / 100
    return result
  } finally {
    URL.revokeObjectURL(url)
  }
}
