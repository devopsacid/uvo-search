import { useRef, useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUnifiedSearch } from '@/api/queries/unifiedSearch'
import type { FirmaHit, ZakazkaHit } from '@/api/queries/unifiedSearch'
import { useKeyboardShortcut } from '@/hooks/useKeyboardShortcut'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

type FlatItem =
  | { kind: 'firma'; hit: FirmaHit }
  | { kind: 'zakazka'; hit: ZakazkaHit }

const ICO_RE = /^\d{8}$/

export function GlobalSearch() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [inputValue, setInputValue] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const navigate = useNavigate()

  const { data, isFetching } = useUnifiedSearch(inputValue)

  const firmy = data?.firmy ?? []
  const zakazky = data?.zakazky ?? []
  const items: FlatItem[] = [
    ...firmy.map((hit): FlatItem => ({ kind: 'firma', hit })),
    ...zakazky.map((hit): FlatItem => ({ kind: 'zakazka', hit })),
  ]
  const hasResults = items.length > 0

  useEffect(() => {
    setActiveIndex(-1)
    setOpen(inputValue.length >= 2 && (hasResults || isFetching))
  }, [inputValue, hasResults, isFetching])

  useKeyboardShortcut('/', () => {
    inputRef.current?.focus()
    inputRef.current?.select()
  })

  const commit = useCallback(
    (index: number) => {
      const item = items[index]
      if (!item) return
      setOpen(false)
      setInputValue('')
      if (item.kind === 'firma') {
        navigate(`/firma/${item.hit.ico}`)
      } else {
        navigate(`/zakazky?selected=${item.hit.id}`)
      }
    },
    [items, navigate],
  )

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (ICO_RE.test(inputValue.trim())) {
        setOpen(false)
        navigate(`/firma/${inputValue.trim()}`)
        setInputValue('')
        return
      }
      if (open && activeIndex >= 0) {
        commit(activeIndex)
        return
      }
      if (open && items.length > 0) {
        commit(0)
        return
      }
      if (inputValue.trim()) {
        setOpen(false)
        navigate(`/hladaj?q=${encodeURIComponent(inputValue.trim())}`)
        setInputValue('')
      }
      return
    }
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const roleLabel = (role: string) =>
    role === 'supplier' ? sk.search.typeSupplier : sk.search.typeProcurer

  return (
    <div className="relative w-64 xl:w-80">
      <input
        ref={inputRef}
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => {
          if (inputValue.length >= 2 && hasResults) setOpen(true)
        }}
        placeholder={sk.globalSearch.placeholder}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        aria-label={sk.globalSearch.placeholder}
        aria-autocomplete="list"
        aria-expanded={open}
      />
      {open && (hasResults || isFetching) && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1 w-full rounded-md border border-border bg-card shadow-lg"
        >
          {firmy.length > 0 && (
            <>
              <li className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {sk.globalSearch.sectionFirmy}
              </li>
              {firmy.map((hit, i) => {
                const flatIndex = i
                return (
                  <li
                    key={`firma-${hit.ico}`}
                    role="option"
                    aria-selected={flatIndex === activeIndex}
                    onMouseDown={() => commit(flatIndex)}
                    onMouseEnter={() => setActiveIndex(flatIndex)}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 px-3 py-2 text-sm',
                      flatIndex === activeIndex ? 'bg-accent' : 'hover:bg-accent/50',
                    )}
                  >
                    <span className="flex shrink-0 gap-1">
                      {hit.roles.map((role) => (
                        <span
                          key={role}
                          className={cn(
                            'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                            role === 'supplier'
                              ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                              : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
                          )}
                        >
                          {roleLabel(role)}
                        </span>
                      ))}
                    </span>
                    <span className="flex-1 truncate text-foreground">{hit.name}</span>
                    <span className="shrink-0 text-[10px] text-muted-foreground">
                      {hit.contract_count}
                    </span>
                  </li>
                )
              })}
            </>
          )}
          {zakazky.length > 0 && (
            <>
              <li className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {sk.globalSearch.sectionZakazky}
              </li>
              {zakazky.map((hit, i) => {
                const flatIndex = firmy.length + i
                return (
                  <li
                    key={`zakazka-${hit.id}`}
                    role="option"
                    aria-selected={flatIndex === activeIndex}
                    onMouseDown={() => commit(flatIndex)}
                    onMouseEnter={() => setActiveIndex(flatIndex)}
                    className={cn(
                      'flex cursor-pointer flex-col gap-0.5 px-3 py-2 text-sm',
                      flatIndex === activeIndex ? 'bg-accent' : 'hover:bg-accent/50',
                    )}
                  >
                    <span className="truncate text-foreground">{hit.title}</span>
                    <span className="flex gap-2 text-[10px] text-muted-foreground">
                      {hit.procurer_name && (
                        <span className="truncate">{hit.procurer_name}</span>
                      )}
                      {hit.value != null && (
                        <span className="shrink-0">
                          {hit.value.toLocaleString('sk-SK', {
                            style: 'currency',
                            currency: 'EUR',
                            maximumFractionDigits: 0,
                          })}
                        </span>
                      )}
                    </span>
                  </li>
                )
              })}
            </>
          )}
          {isFetching && (
            <li className="px-3 py-2 text-xs text-muted-foreground">{sk.common.loading}</li>
          )}
        </ul>
      )}
    </div>
  )
}
