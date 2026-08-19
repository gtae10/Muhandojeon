import { useEffect, useRef, useState } from 'react'

function ChevronIcon({ open }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      className={`shrink-0 transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
    >
      <path d="M2.5 4.5L6 8l3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/**
 * 브랜드 톤에 맞춘 커스텀 셀렉트. 네이티브 <select> 대신 버튼(trigger) +
 * 절대위치 목록(listbox)으로 구성해 열렸을 때도 브라우저 기본 스타일이 끼어들지 않는다.
 *
 * @param {string} value
 * @param {(value: string) => void} onChange
 * @param {{value: string, label: string}[]} options
 * @param {string} [placeholder]
 * @param {boolean} [disabled]
 */
export default function Select({ value, onChange, options, placeholder = '선택하세요', disabled = false }) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(-1)
  const rootRef = useRef(null)
  const listRef = useRef(null)

  const selectedIndex = options.findIndex((o) => o.value === value)
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : null

  useEffect(() => {
    if (!open) return
    function onPointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  useEffect(() => {
    if (open) setHighlighted(selectedIndex >= 0 ? selectedIndex : 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (open && highlighted >= 0) {
      listRef.current?.children[highlighted]?.scrollIntoView({ block: 'nearest' })
    }
  }, [open, highlighted])

  function commit(index) {
    const opt = options[index]
    if (!opt) return
    onChange(opt.value)
    setOpen(false)
  }

  function handleTriggerKeyDown(e) {
    if (disabled) return
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        setOpen(true)
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((h) => Math.min(options.length - 1, h + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((h) => Math.max(0, h - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      commit(highlighted)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={handleTriggerKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="w-full h-14 flex items-center justify-between gap-3 bg-[var(--color-surface)] border border-[var(--color-border)] px-4 text-base text-left text-[var(--color-text)] transition-colors duration-150 hover:border-[var(--color-accent)]/40 disabled:opacity-50"
      >
        <span className={`truncate ${selectedOption ? '' : 'text-[var(--color-muted)]'}`}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <ul
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          className="absolute z-20 left-0 right-0 mt-2 max-h-72 overflow-y-auto bg-[var(--color-surface-raised)] border border-[var(--color-border)] py-1 [animation:select-in_150ms_ease-out]"
        >
          {options.map((opt, i) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              onMouseEnter={() => setHighlighted(i)}
              onClick={() => commit(i)}
              className={`relative pl-5 pr-4 py-3 text-sm cursor-pointer transition-colors duration-100 ${
                i === highlighted ? 'bg-[var(--color-accent-soft)]' : ''
              } ${opt.value === value ? 'text-[var(--color-accent)]' : 'text-[var(--color-text)]'}`}
            >
              {i === highlighted && (
                <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-[var(--color-accent)]" />
              )}
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
