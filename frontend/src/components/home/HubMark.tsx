/** The hub's own mark: beside the Super Agent's answers, and wherever it is offered. */
export function HubMark({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden="true">
      <circle cx="20" cy="20" r="18" fill="#e60000" />
      <circle cx="20" cy="20" r="9.5" fill="#fff" />
      <circle cx="20" cy="20" r="5.5" fill="#e60000" />
    </svg>
  )
}
