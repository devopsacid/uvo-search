import { useParams, Link } from 'react-router-dom'
import { useAnalyticsConcentration } from '@/api/queries/analytics'
import { useCompanyProfile } from '@/api/queries/companies'
import { HhiBadge } from '@/components/analytics/HhiBadge'
import { SpendByYearChart } from '@/components/charts/SpendByYearChart'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton, SkeletonRow } from '@/components/ui/Skeleton'
import { defaultRange, type AnalyticsFilters } from '@/lib/analyticsFilters'
import { analyticsLink } from '@/lib/analyticsLinks'
import { formatCurrency, formatDate, formatNumber, formatPercent } from '@/lib/utils'
import sk from '@/i18n/sk'

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  )
}

/** HHI / CR4 of a procurer's suppliers over the analytics default period (same numbers as the linked dashboard). */
function ProcurerConcentrationCard({ ico }: { ico: string }) {
  const filters: AnalyticsFilters = { ...defaultRange(), procurer_ico: ico }
  const { data, isLoading, isError } = useAnalyticsConcentration(filters, 'supplier')
  const t = sk.analytics.concentration

  if (isError || (data && data.entity_count === 0)) return null
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">{sk.company.supplierConcentration}</h2>
      {isLoading || !data ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">{t.hhi}</dt>
              <dd className="mt-1 flex items-center gap-2 text-xl font-semibold tabular-nums text-foreground">
                {formatNumber(Math.round(data.hhi))}
                <HhiBadge band={data.hhi_band} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">{t.cr4}</dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">{formatPercent(data.cr4_pct)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">{t.cr10}</dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">{formatPercent(data.cr10_pct)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">{t.entityCount}</dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">{formatNumber(data.entity_count)}</dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">
            {sk.company.concentrationPeriod.replace('{from}', formatDate(filters.date_from)).replace('{to}', formatDate(filters.date_to))}{' '}
            <Link to={analyticsLink('concentration', { procurer_ico: ico })} className="text-primary hover:underline">
              {sk.company.concentrationLink}
            </Link>
          </p>
        </>
      )}
    </div>
  )
}

export function CompanyOverviewTab() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data: profile, isLoading } = useCompanyProfile(safeIco)

  const supplierCount = profile?.stats.as_supplier?.contract_count ?? 0
  const procurerCount = profile?.stats.as_procurer?.contract_count ?? 0
  const totalContracts = supplierCount + procurerCount

  const supplierValue = profile?.stats.as_supplier?.total_value ?? 0
  const procurerValue = profile?.stats.as_procurer?.total_value ?? 0
  const totalValue = supplierValue + procurerValue

  const lastSupplier = profile?.stats.as_supplier?.last_contract_at ?? null
  const lastProcurer = profile?.stats.as_procurer?.last_contract_at ?? null
  const lastContractAt =
    lastSupplier && lastProcurer
      ? lastSupplier > lastProcurer
        ? lastSupplier
        : lastProcurer
      : (lastSupplier ?? lastProcurer)

  // Derive unique top partners from top_contracts counterparty data
  const topPartners = (() => {
    if (!profile?.top_contracts) return []
    const map = new Map<string, { name: string; ico: string; count: number }>()
    for (const c of profile.top_contracts) {
      if (!c.counterparty_ico) continue
      const existing = map.get(c.counterparty_ico)
      if (existing) {
        existing.count++
      } else {
        map.set(c.counterparty_ico, {
          name: c.counterparty_name ?? c.counterparty_ico,
          ico: c.counterparty_ico,
          count: 1,
        })
      }
    }
    return Array.from(map.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
  })()

  // SpendByYearChart expects { year, total_value } — company's SpendByYear has the same shape
  const spendData = (profile?.spend_by_year ?? []).map((s) => ({
    year: s.year,
    total_value: s.total_value,
  }))

  return (
    <div className="space-y-6">
      {/* Link into the analytics dashboards, one per role the company has */}
      {!isLoading && (procurerCount > 0 || supplierCount > 0) && (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {procurerCount > 0 && (
            <Link to={analyticsLink('overview', { procurer_ico: safeIco })} className="text-primary hover:underline">
              {procurerCount > 0 && supplierCount > 0 ? sk.company.analyticsAsProcurer : sk.company.analyticsLink}
            </Link>
          )}
          {supplierCount > 0 && (
            <Link to={analyticsLink('overview', { supplier_ico: safeIco })} className="text-primary hover:underline">
              {procurerCount > 0 && supplierCount > 0 ? sk.company.analyticsAsSupplier : sk.company.analyticsLink}
            </Link>
          )}
        </p>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-4">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard label={sk.company.kpiContracts} value={formatNumber(totalContracts)} />
            <KpiCard label={sk.company.kpiValue} value={formatCurrency(totalValue)} />
            <KpiCard label={sk.company.kpiLast} value={formatDate(lastContractAt)} />
          </>
        )}
      </div>

      {/* Spend by year */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">{sk.suppliers.sectionSpend}</h2>
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <SpendByYearChart data={spendData} />
        )}
      </div>

      {procurerCount > 0 && <ProcurerConcentrationCard ico={safeIco} />}

      {/* Top contracts */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{sk.company.topContracts}</h2>
        </div>
        <Table>
          <TableHeader>
            <tr>
              <TableHead>{sk.search.colTitle}</TableHead>
              <TableHead className="text-right">{sk.search.colValue}</TableHead>
              <TableHead>{sk.search.colYear}</TableHead>
              <TableHead>{sk.company.colCounterparty}</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={4} />)
              : (profile?.top_contracts ?? []).slice(0, 5).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="max-w-xs">
                      <span className="line-clamp-2 text-sm">{c.title}</span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.value != null ? formatCurrency(c.value) : '—'}
                    </TableCell>
                    <TableCell>{c.year ?? '—'}</TableCell>
                    <TableCell>
                      {c.counterparty_ico ? (
                        <Link
                          to={`/company/${c.counterparty_ico}`}
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          {c.counterparty_name || c.counterparty_ico}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">
                          {c.counterparty_name || '—'}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>

      {/* Top partners (derived from top_contracts counterparties) */}
      {topPartners.length > 0 && (
        <div className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">{sk.company.topPartners}</h2>
          </div>
          <div className="divide-y divide-border">
            {topPartners.map((p) => (
              <div key={p.ico} className="flex items-center justify-between px-4 py-2.5">
                <Link
                  to={`/company/${p.ico}`}
                  className="text-sm text-primary underline-offset-2 hover:underline"
                >
                  {p.name}
                </Link>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {formatNumber(p.count)} {sk.company.contractsUnit}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
