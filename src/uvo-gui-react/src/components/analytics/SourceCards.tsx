import type { CoverageSource, CoverageStatus } from '@/api/types'
import { cn, formatAge, formatDate, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

const STATUS_STYLES: Record<CoverageStatus, string> = {
  healthy: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  warning: 'bg-amber-50 text-amber-900 border-amber-200',
  stale: 'bg-rose-50 text-rose-800 border-rose-200',
  legacy: 'bg-slate-100 text-slate-700 border-slate-300',
  unknown: 'bg-slate-100 text-slate-700 border-slate-300',
}

export function SourceCards({ sources }: { sources: CoverageSource[] }) {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {sources.map((s) => (
        <li key={s.source} className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">
              {sk.analytics.filters.sources[s.source] ?? s.source}
            </h3>
            <span
              className={cn(
                'rounded-full border px-2 py-0.5 text-xs font-medium',
                STATUS_STYLES[s.status] ?? STATUS_STYLES.unknown,
              )}
            >
              {sk.analytics.pokrytie.status[s.status] ?? s.status}
            </span>
          </div>
          <dl className="mt-3 space-y-1.5 text-sm">
            <Row label={sk.analytics.pokrytie.noticesTotal} value={formatNumber(s.notices_total)} />
            <Row label={sk.analytics.pokrytie.contractAwards} value={formatNumber(s.contract_awards)} />
            <Row
              label={sk.analytics.pokrytie.lastUpdate}
              value={formatAge(s.age_seconds, sk.analytics.pokrytie.never)}
            />
            <Row label={sk.analytics.pokrytie.lastPublication} value={formatDate(s.last_publication_date)} />
          </dl>
        </li>
      ))}
    </ul>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums text-foreground">{value}</dd>
    </div>
  )
}
