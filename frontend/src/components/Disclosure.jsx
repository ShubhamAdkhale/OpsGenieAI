import { useState } from 'react'

/**
 * Progressive disclosure.
 *
 * Detail lives behind a summary row: the count and a one-line summary stay
 * visible so nothing is hidden, but the rows only render when someone asks for
 * them. The closed state is deliberately quiet — a single line of text with a
 * chevron, not a card-within-a-card — so a column of six collapsed sections
 * reads as a contents list rather than six more things to look at.
 */
export default function Disclosure({
  title,
  summary,
  badge,
  defaultOpen = false,
  children,
  className = '',
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section className={`card ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 rounded-card px-5 py-3.5 text-left transition-colors hover:bg-surface-hover"
      >
        <span
          className={`text-[10px] text-ink-3 transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        >
          ▶
        </span>
        <span className="card-title">{title}</span>
        {badge != null && (
          <span className="rounded-md bg-surface-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-3">
            {badge}
          </span>
        )}
        {summary && (
          <span className="ml-auto hidden truncate text-xs text-ink-3 sm:block">{summary}</span>
        )}
      </button>
      {open && <div className="border-t border-line p-5">{children}</div>}
    </section>
  )
}
