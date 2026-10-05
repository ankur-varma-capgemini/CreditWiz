import { ArrowUp, Loader2, UserRound } from 'lucide-react'
import { useEffect, useRef } from 'react'

interface Props {
  value: string
  onChange: (value: string) => void
  onSend: (text: string) => void
  busy: boolean
  /** The role answers are tuned to, shown so nobody wonders why results differ. */
  personaLabel?: string
  placeholder: string
  autoFocus?: boolean
}

/** Where a question is typed. Enter sends; Shift and Enter start a new line. */
export function Composer({ value, onChange, onSend, busy, personaLabel, placeholder, autoFocus }: Props) {
  const input = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (autoFocus) input.current?.focus()
  }, [autoFocus])

  // One line to start; grows with what is typed, up to the CSS max-height.
  useEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  return (
    <form
      className="composer"
      aria-label="Ask the Super Agent"
      onSubmit={(e) => {
        e.preventDefault()
        onSend(value)
      }}
    >
      <textarea
        ref={input}
        className="composer__input"
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            onSend(value)
          }
        }}
        placeholder={placeholder}
        aria-label="Ask the Super Agent"
      />
      <div className="composer__tools">
        {personaLabel && (
          <span className="composer__pill" title="Answers are tuned to this role">
            <UserRound size={13} strokeWidth={2.2} aria-hidden="true" /> As {personaLabel}
          </span>
        )}
        <span className="composer__hint">Enter to send, Shift and Enter for a new line</span>
        <button
          type="submit"
          className="composer__send"
          disabled={busy || !value.trim()}
          aria-label="Send"
          title="Send"
        >
          {busy ? <Loader2 className="spin" size={16} /> : <ArrowUp size={16} strokeWidth={2.4} />}
        </button>
      </div>
    </form>
  )
}
