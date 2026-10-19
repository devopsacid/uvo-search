import { useEffect, useId, useState } from 'react'
import { useAnalyticsCpv } from '@/api/queries/analytics'
import { EntityFilterPicker } from '@/components/analytics/EntityFilterPicker'
import { useAnalyticsFilters } from '@/hooks/useAnalyticsFilters'
import { PRESET_IDS, SOURCES } from '@/lib/analyticsFilters'
import { cn } from '@/lib/utils'
import sk from '@/i18n/sk'

const INPUT =
  'rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring'
const BUTTON =
  'rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring'
const ISO = /^\d{4}-\d{2}-\d{2}$/

/** The one sticky filter bar shared by all analytics pages (spec §5.1). All state lives in the URL. */
export function AnalyticsFilterBar() {
  const { filters, rangeProblem, isDefault, preset, setFilters, applyPreset, reset, currentUrl } =
    useAnalyticsFilters()
  const [names, setNames] = useState<Record<string, string>>({})
  const [cpvDraft, setCpvDraft] = useState(filters.cpv ?? '')
  const [copied, setCopied] = useState(false)
  const listId = useId()

  // Keep the draft in step with URL-driven changes (drill-down, reset, back button).
  useEffect(() => setCpvDraft(filters.cpv ?? ''), [filters.cpv])

  const cpvOptions = useAnalyticsCpv({ ...filters, cpv: undefined }, 'division')
  const divisions = cpvOptions.data?.items ?? []

  function commitCpv(raw: string) {
    const digits = raw.replace(/\D/g, '')
    if (digits === (filters.cpv ?? '')) return
    if (digits === '' || (digits.length >= 2 && digits.length <= 8)) setFilters({ cpv: digits || undefined })
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(currentUrl())
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section
      aria-label={sk.analytics.filters.label}
      className="sticky top-0 z-20 -mx-4 border-b border-border bg-background/95 px-4 py-3 backdrop-blur"
    >
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div role="group" aria-label={sk.analytics.filters.period} className="flex flex-wrap items-center gap-1.5">
          {PRESET_IDS.map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed={preset === id}
              onClick={() => applyPreset(id)}
              className={cn(
                BUTTON,
                'px-2.5 py-1 text-xs',
                preset === id && 'border-primary bg-primary text-primary-foreground hover:bg-primary',
              )}
            >
              {sk.analytics.filters.presets[id]}
            </button>
          ))}
        </div>

        <label className="space-y-1">
          <span className="block text-xs text-muted-foreground">{sk.analytics.filters.dateFrom}</span>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => ISO.test(e.target.value) && setFilters({ date_from: e.target.value })}
            aria-invalid={rangeProblem ? true : undefined}
            className={INPUT}
          />
        </label>
        <label className="space-y-1">
          <span className="block text-xs text-muted-foreground">{sk.analytics.filters.dateTo}</span>
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => ISO.test(e.target.value) && setFilters({ date_to: e.target.value })}
            aria-invalid={rangeProblem ? true : undefined}
            className={INPUT}
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-3">
        <label className="space-y-1">
          <span className="block text-xs text-muted-foreground">{sk.analytics.filters.cpv}</span>
          <input
            type="text"
            inputMode="numeric"
            list={listId}
            value={cpvDraft}
            maxLength={8}
            placeholder={sk.analytics.filters.cpvPlaceholder}
            onChange={(e) => {
              const v = e.target.value.replace(/\D/g, '')
              setCpvDraft(v)
              // Picking a datalist entry fires a change with the full division code.
              if (divisions.some((d) => d.prefix === v)) commitCpv(v)
            }}
            onBlur={() => commitCpv(cpvDraft)}
            onKeyDown={(e) => e.key === 'Enter' && commitCpv(cpvDraft)}
            className={cn(INPUT, 'w-40')}
          />
          <datalist id={listId}>
            {divisions.map((d) => (
              <option key={d.prefix} value={d.prefix}>
                {d.label_sk}
              </option>
            ))}
          </datalist>
        </label>

        <label className="space-y-1">
          <span className="block text-xs text-muted-foreground">{sk.analytics.filters.source}</span>
          <select
            value={filters.source ?? ''}
            onChange={(e) => setFilters({ source: e.target.value || undefined })}
            className={cn(INPUT, 'w-44')}
          >
            <option value="">{sk.common.all}</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {sk.analytics.filters.sources[s]}
              </option>
            ))}
          </select>
        </label>

        <EntityFilterPicker
          label={sk.analytics.filters.procurer}
          role="procurer"
          ico={filters.procurer_ico}
          name={filters.procurer_ico ? names[filters.procurer_ico] : undefined}
          onSelect={(ico, name) => {
            setNames((n) => ({ ...n, [ico]: name }))
            setFilters({ procurer_ico: ico })
          }}
          onClear={() => setFilters({ procurer_ico: undefined })}
        />
        <EntityFilterPicker
          label={sk.analytics.filters.supplier}
          role="supplier"
          ico={filters.supplier_ico}
          name={filters.supplier_ico ? names[filters.supplier_ico] : undefined}
          onSelect={(ico, name) => {
            setNames((n) => ({ ...n, [ico]: name }))
            setFilters({ supplier_ico: ico })
          }}
          onClear={() => setFilters({ supplier_ico: undefined })}
        />

        <div className="ml-auto flex items-center gap-2">
          {!isDefault && (
            <button type="button" onClick={reset} className={BUTTON}>
              {sk.analytics.filters.reset}
            </button>
          )}
          <button type="button" onClick={() => void copyLink()} className={BUTTON}>
            {sk.analytics.filters.copyLink}
          </button>
        </div>
      </div>

      <p role="status" className="sr-only">
        {copied ? sk.analytics.filters.linkCopied : ''}
      </p>
      {copied && (
        <p aria-hidden="true" className="mt-2 text-xs text-muted-foreground">
          {sk.analytics.filters.linkCopied}
        </p>
      )}
      {rangeProblem && (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {rangeProblem === 'reversed' ? sk.analytics.filters.rangeReversed : sk.analytics.filters.rangeSpan}
        </p>
      )}
    </section>
  )
}
