/** FastChip mark: a packaged die with a signal trace. Same drawing as public/favicon.svg. */
export function Logo({ className = 'size-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <rect x="7" y="7" width="18" height="18" rx="3.5" className="fill-brand-600 dark:fill-brand-500" />
      <path
        d="M12 3v3M16 3v3M20 3v3M12 26v3M16 26v3M20 26v3M3 12h3M3 16h3M3 20h3M26 12h3M26 16h3M26 20h3"
        className="stroke-brand-600 dark:stroke-brand-500"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M12 19.5l3-7 2 4.5 1.2-2H20" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
