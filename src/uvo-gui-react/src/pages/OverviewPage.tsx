import { Link } from 'react-router-dom'
import {
  useDashboardSummary,
  useRecent,
  useSpendByYear,
  useTopProcurers,
  useTopSuppliers,
} from '@/api/queries/dashboard'
import { useSupplier } from '@/api/queries/suppliers'
import { useProcurer } from '@/api/queries/procurers'
import { useCompanyPin } from '@/context/CompanyPinContext'
import { EntityAutocomplete } from '@/components/search/EntityAutocomplete'
import { KpiCard } from '@/components/ui/KpiCard'
import { Skeleton, SkeletonRow } from '@/components/ui/Skeleton'
import { SpendByYearChart } from '@/components/charts/SpendByYearChart'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { EntityLink } from '@/components/entity/EntityLink'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 text-sm font-semibold text-foreground">{children}</h2>
}

function SectionCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-border bg-card p-4 ${className ?? ''}`}>
      {children}
    </div>
  )
}

function formatMillions(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)} tis.`
  return String(v)
}

export function OverviewPage() {
  const { ico, type, setPin } = useCompanyPin()

  const { data: summary, isLoading: summaryLoading, isError, error, refetch } = useDashboardSummary(ico ?? undefined, type ?? undefined)
  const { data: spendByYear, isLoading: spendLoading } = useSpendByYear(ico ?? undefined, type ?? undefined)
  const { data: topSuppliers, isLoading: suppliersLoading } = useTopSuppliers(10)
  const { data: topProcurers, isLoading: procurersLoading } = useTopProcurers(10)
  const { data: recent, isLoading: recentLoading } = useRecent(8, ico ?? undefined, type ?? undefined)
  const { data: supplierDetail } = useSupplier(ico ?? '')
  const { data: procurerDetail } = useProcurer(ico ?? '')

  if (isError) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center">
        <p className="text-muted-foreground">{sk.overview.error}</p>
        {error instanceof Error && (
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        )}
        <button
          onClick={() => void refetch()}
          className="mt-4 text-sm text-primary underline-offset-4 hover:underline"
        >
          {sk.common.retry}
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-semibold text-foreground">{sk.overview.title}</h1>
        <EntityAutocomplete
          placeholder={sk.pin.placeholder}
          className="w-72"
          onSelect={(selectedIco, selectedType, selectedName) =>
            setPin(selectedIco, selectedName, selectedType)
          }
        />
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {summaryLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard
              label={sk.overview.totalValue}
              value={formatCurrency(summary?.total_value ?? 0)}
              pct={summary?.deltas['total_value']?.pct}
            />
            <KpiCard
              label={sk.overview.contractCount}
              value={formatNumber(summary?.contract_count ?? 0)}
              pct={summary?.deltas['contract_count']?.pct}
            />
            <KpiCard
              label={sk.overview.avgValue}
              value={formatCurrency(summary?.avg_value ?? 0)}
              pct={summary?.deltas['avg_value']?.pct}
            />
            <KpiCard
              label={sk.overview.activeSuppliers}
              value={formatNumber(summary?.active_suppliers ?? 0)}
            />
          </>
        )}
      </div>

      {/* Spend by year */}
      <SectionCard>
        <SectionTitle>{sk.overview.sectionSpend}</SectionTitle>
        {spendLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <SpendByYearChart data={spendByYear ?? []} />
        )}
      </SectionCard>

      {/* Top suppliers + Top procurers (global) OR top partners (pinned) */}
      {ico ? (
        <div className="grid gap-6 md:grid-cols-2">
          <SectionCard>
            <SectionTitle>
              {type === 'supplier' ? sk.overview.sectionTopProcurers : sk.overview.sectionTopSuppliers}
            </SectionTitle>
            {(() => {
              const partners = type === 'supplier'
                ? supplierDetail?.top_procurers
                : procurerDetail?.top_suppliers
              const isLoading = type === 'supplier' ? !supplierDetail : !procurerDetail
              if (isLoading) return <Skeleton className="h-48 w-full" />
              if (!partners?.length) return <p className="text-sm text-muted-foreground">{sk.common.noData}</p>
              return (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={partners} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis type="number" tickFormatter={formatMillions} tick={{ fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 10 }}
                      width={100}
                      tickFormatter={(v: string) => (v.length > 14 ? v.slice(0, 14) + '…' : v)}
                    />
                    <Tooltip formatter={(v: number) => [formatCurrency(v), 'Objem']} />
                    <Bar dataKey="total_value" fill="hsl(var(--primary))" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )
            })()}
          </SectionCard>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          <SectionCard>
            <SectionTitle>{sk.overview.sectionTopSuppliers}</SectionTitle>
            {suppliersLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : (topSuppliers?.length ?? 0) > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={topSuppliers}
                  layout="vertical"
                  margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis type="number" tickFormatter={formatMillions} tick={{ fontSize: 10 }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    width={100}
                    tickFormatter={(v: string) => (v.length > 14 ? v.slice(0, 14) + '…' : v)}
                  />
                  <Tooltip formatter={(v: number) => [formatCurrency(v), 'Objem']} />
                  <Bar dataKey="total_value" fill="hsl(var(--primary))" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">{sk.common.noData}</p>
            )}
          </SectionCard>

          <SectionCard>
            <SectionTitle>{sk.overview.sectionTopProcurers}</SectionTitle>
            {procurersLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : (topProcurers?.length ?? 0) > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={topProcurers}
                  layout="vertical"
                  margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis type="number" tickFormatter={formatMillions} tick={{ fontSize: 10 }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 10 }}
                    width={100}
                    tickFormatter={(v: string) => (v.length > 14 ? v.slice(0, 14) + '…' : v)}
                  />
                  <Tooltip formatter={(v: number) => [formatCurrency(v), 'Objem']} />
                  <Bar dataKey="total_spend" fill="hsl(var(--primary))" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-muted-foreground">{sk.common.noData}</p>
            )}
          </SectionCard>
        </div>
      )}

      {/* Recent contracts */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <SectionTitle>{sk.overview.sectionRecent}</SectionTitle>
        </div>
        <Table>
          <TableHeader>
            <tr>
              <TableHead>{sk.search.colTitle}</TableHead>
              <TableHead>{sk.search.colProcurer}</TableHead>
              <TableHead className="text-right">{sk.search.colValue}</TableHead>
              <TableHead>{sk.search.colYear}</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {recentLoading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={4} />)
              : recent?.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="max-w-xs">
                      <Link
                        to={`/search?q=${encodeURIComponent(c.title)}`}
                        className="line-clamp-2 text-sm hover:underline"
                      >
                        {c.title || '—'}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {c.procurer_ico ? (
                        <EntityLink ico={c.procurer_ico} name={c.procurer_name} type="procurer" />
                      ) : (
                        <span className="text-muted-foreground">{c.procurer_name || '—'}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(c.value)}
                    </TableCell>
                    <TableCell>{c.year}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
