import { useRef, useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEntityAutocomplete } from '@/api/queries/search'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useKeyboardShortcut } from '@/hooks/useKeyboardShortcut'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

interface EntityAutocompleteProps {
  placeholder?: string
  className?: string
  autoFocus?: boolean
  onSelect?: (ico: string, type: 'supplier' | 'procurer', name: string) => void
}

export function EntityAutocomplete({
  placeholder,
  className,
  autoFocus,
  onSelect,
}: EntityAutocompleteProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [inputValue, setInputValue] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const navigate = useNavigate()

  const debouncedQuery = useDebouncedValue(inputValue, 250)
  const { data, isFetching } = useEntityAutocomplete(debouncedQuery)
  const hits = data?.items ?? []

  // '/' focuses the search input globally
  useKeyboardShortcut('/', () => {
    inputRef.current?.focus()
    inputRef.current?.select()
  })

  useEffect(() => {
    setActiveIndex(-1)
    setOpen(debouncedQuery.length >= 2)
  }, [debouncedQuery])

  const commit = useCallback(
    (index: number) => {
      const hit = hits[index]
      if (!hit) return
      setOpen(false)
      setInputValue('')
      if (onSelect) {
        onSelect(hit.ico, hit.type as 'supplier' | 'procurer', hit.name)
      } else {
        navigate(hit.type === 'supplier' ? `/suppliers/${hit.ico}` : `/procurers/${hit.ico}`)
      }
    },
    [hits, navigate, onSelect],
  )

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, hits.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0) commit(activeIndex)
      else if (hits.length > 0) commit(0)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const typeLabel = (type: string) =>
    type === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer

  return (
    <div className={cn('relative', className)}>
      <input
        ref={inputRef}
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => { if (debouncedQuery.length >= 2) setOpen(true) }}
        placeholder={placeholder ?? sk.search.autocompletePlaceholder}
        autoFocus={autoFocus}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        aria-label={sk.search.autocompletePlaceholder}
        aria-autocomplete="list"
        aria-expanded={open}
      />
      {open && hits.length > 0 && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 w-full rounded-md border border-border bg-card shadow-lg"
        >
          {hits.map((hit, i) => (
            <li
              key={`${hit.type}-${hit.ico}`}
              role="option"
              aria-selected={i === activeIndex}
              onMouseDown={() => commit(i)}
              onMouseEnter={() => setActiveIndex(i)}
              className={cn(
                'flex cursor-pointer items-center gap-2 px-3 py-2 text-sm',
                i === activeIndex ? 'bg-accent' : 'hover:bg-accent/50',
              )}
            >
              <span
                className={cn(
                  'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                  hit.type === 'supplier'
                    ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
                )}
              >
                {typeLabel(hit.type)}
              </span>
              <span className="flex-1 truncate text-foreground">{hit.name}</span>
              <span className="shrink-0 text-[10px] text-muted-foreground">{hit.ico}</span>
              <span className="shrink-0 text-[10px] text-muted-foreground">{hit.contract_count}</span>
            </li>
          ))}
          {isFetching && (
            <li className="px-3 py-2 text-xs text-muted-foreground">{sk.common.loading}</li>
          )}
        </ul>
      )}
    </div>
  )
}
