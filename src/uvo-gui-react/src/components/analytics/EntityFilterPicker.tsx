import { useId, useMemo, useState } from 'react'
import { useEntityAutocomplete } from '@/api/queries/search'
import { SEARCH_DEBOUNCE_MS, useDebouncedValue } from '@/hooks/useDebouncedValue'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

interface EntityFilterPickerProps {
  label: string
  role: 'procurer' | 'supplier'
  /** Selected IČO (from the URL). */
  ico?: string
  /** Display name when we know it (picked in this session); otherwise the IČO is shown. */
  name?: string
  onSelect: (ico: string, name: string) => void
  onClear: () => void
}

/**
 * Single-role entity picker for the filter bar. The shared `EntityAutocomplete` navigates and binds
 * the global "/" shortcut, neither of which is wanted here, so this is a small combobox on the same
 * `useEntityAutocomplete` query, restricted to one role.
 */
export function EntityFilterPicker({ label, role, ico, name, onSelect, onClear }: EntityFilterPickerProps) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const listId = useId()
  const debounced = useDebouncedValue(text, SEARCH_DEBOUNCE_MS)
  const { data, isFetching } = useEntityAutocomplete(debounced)
  const hits = useMemo(() => (data?.items ?? []).filter((h) => h.type === role), [data, role])
  const showList = open && debounced.length >= 2

  function commit(index: number) {
    const hit = hits[index]
    if (!hit) return
    setText('')
    setOpen(false)
    setActive(-1)
    onSelect(hit.ico, hit.name)
  }

  if (ico) {
    const display = name ? `${name} (${ico})` : sk.analytics.filters.icoValue.replace('{ico}', ico)
    return (
      <div className="space-y-1">
        <span className="block text-xs text-muted-foreground">{label}</span>
        <span className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-accent py-1 pl-2.5 pr-1 text-sm text-foreground">
          <span className="truncate" title={display}>
            {display}
          </span>
          <button
            type="button"
            onClick={onClear}
            aria-label={sk.analytics.filters.removeFilter.replace('{name}', label)}
            className="rounded px-1.5 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden="true">×</span>
          </button>
        </span>
      </div>
    )
  }

  return (
    <div className="relative space-y-1">
      <label className="block space-y-1">
        <span className="block text-xs text-muted-foreground">{label}</span>
        <input
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          value={text}
          placeholder={sk.analytics.filters.entityPlaceholder}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
            setActive(-1)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setOpen(true)
              setActive((i) => Math.min(i + 1, hits.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((i) => Math.max(i - 1, 0))
            } else if (e.key === 'Enter' && showList && hits.length > 0) {
              e.preventDefault()
              commit(active >= 0 ? active : 0)
            } else if (e.key === 'Escape') {
              setOpen(false)
            }
          }}
          className="w-full min-w-[12rem] rounded-md border border-input bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </label>
      <ul
        id={listId}
        role="listbox"
        aria-label={label}
        hidden={!showList}
        className="absolute z-30 mt-1 max-h-64 w-full min-w-[16rem] overflow-auto rounded-md border border-border bg-card shadow-lg"
      >
        {hits.map((hit, i) => (
          <li
            key={hit.ico}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={i === active}
            onMouseDown={(e) => {
              e.preventDefault()
              commit(i)
            }}
            onMouseEnter={() => setActive(i)}
            className={cn(
              'flex cursor-pointer items-center gap-2 px-3 py-2 text-sm',
              i === active ? 'bg-accent' : 'hover:bg-accent/50',
            )}
          >
            <span className="flex-1 truncate text-foreground">{hit.name}</span>
            <span className="shrink-0 text-xs text-muted-foreground">{hit.ico}</span>
          </li>
        ))}
        {showList && !isFetching && hits.length === 0 && (
          <li className="px-3 py-2 text-xs text-muted-foreground">{sk.analytics.filters.noEntityHits}</li>
        )}
        {showList && isFetching && hits.length === 0 && (
          <li className="px-3 py-2 text-xs text-muted-foreground">{sk.common.loading}</li>
        )}
      </ul>
    </div>
  )
}
