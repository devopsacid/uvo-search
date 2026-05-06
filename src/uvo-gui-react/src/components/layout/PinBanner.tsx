import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCompanyPin } from '@/context/CompanyPinContext'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

export function PinBanner() {
  const { ico, name, type, clearPin } = useCompanyPin()
  const navigate = useNavigate()
  const [copied, setCopied] = useState(false)

  if (!ico || !type) return null

  const typeLabel = type === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer
  const href = type === 'supplier' ? `/suppliers/${ico}` : `/procurers/${ico}`

  function copyLink() {
    const params = new URLSearchParams({ pin_ico: ico!, pin_type: type! })
    if (name) params.set('pin_name', name)
    const url = `${window.location.origin}/?${params.toString()}`
    void navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div role="status" className="flex items-center gap-2 border-b border-border bg-accent/60 px-4 py-1.5 text-xs">
      <span
        className={cn(
          'shrink-0 rounded px-1.5 py-0.5 font-medium uppercase tracking-wide',
          type === 'supplier'
            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
            : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
        )}
      >
        {typeLabel}
      </span>
      <button
        onClick={() => navigate(href)}
        className="flex-1 truncate text-left font-medium text-foreground hover:underline"
      >
        {name ?? ''}
      </button>
      <span className="text-muted-foreground">{ico}</span>
      <button
        onClick={copyLink}
        aria-label={sk.pin.copyLink}
        title={sk.pin.copyLink}
        className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        {copied ? '✓' : '⎘'}
      </button>
      <button
        onClick={clearPin}
        aria-label={sk.pin.clear}
        className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        ×
      </button>
    </div>
  )
}
