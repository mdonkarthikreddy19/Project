import { useEffect, useRef } from 'react'

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Fades and lifts its children in the first time they scroll into view.
export function Reveal({ as: Tag = 'div', delay = 0, className = '', children, ...rest }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    // above the fold: show it now rather than waiting on the observer (it never fires in a background tab)
    if (reduced() || !('IntersectionObserver' in window) || el.getBoundingClientRect().top < window.innerHeight * 0.9) {
      requestAnimationFrame(() => el.classList.add('is-in'))
      setTimeout(() => el.classList.add('is-in'), 400)
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('is-in')
          io.disconnect()
        }
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.12 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <Tag ref={ref} className={`reveal ${className}`} style={{ '--d': delay }} {...rest}>
      {children}
    </Tag>
  )
}

// Thin bar under the nav showing how far down the page you are.
export function PageProgress() {
  const ref = useRef(null)
  useEffect(() => {
    let frame = 0
    const update = () => {
      frame = 0
      const max = document.documentElement.scrollHeight - window.innerHeight
      ref.current?.style.setProperty('--p', max > 0 ? (window.scrollY / max).toFixed(4) : 0)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])
  return <div className="page-progress" ref={ref} aria-hidden="true" />
}
