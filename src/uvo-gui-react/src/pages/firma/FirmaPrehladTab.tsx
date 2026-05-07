import { useParams, Link } from 'react-router-dom'
import { useFirmaProfile } from '@/api/queries/firma'
import { SpendByYearChart } from '@/components/charts/SpendByYearChart'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { Skeleton, SkeletonRow } from '@/components/ui/Skeleton'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  )
}

export function FirmaPrehladTab() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data: profile, isLoading } = useFirmaProfile(safeIco)

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

  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString('sk-SK') : '—'

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

  // SpendByYearChart expects { year, total_value } — firma's SpendByYear has the same shape
  const spendData = (profile?.spend_by_year ?? []).map((s) => ({
    year: s.year,
    total_value: s.total_value,
  }))

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-4">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
          ))
        ) : (
          <>
            <KpiCard label={sk.firma.kpiZakazky} value={formatNumber(totalContracts)} />
            <KpiCard label={sk.firma.kpiHodnota} value={formatCurrency(totalValue)} />
            <KpiCard label={sk.firma.kpiPosledna} value={formatDate(lastContractAt)} />
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

      {/* Top contracts */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">{sk.firma.topContracts}</h2>
        </div>
        <Table>
          <TableHeader>
            <tr>
              <TableHead>{sk.search.colTitle}</TableHead>
              <TableHead className="text-right">{sk.search.colValue}</TableHead>
              <TableHead>{sk.search.colYear}</TableHead>
              <TableHead>Protistrana</TableHead>
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
                          to={`/firma/${c.counterparty_ico}`}
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
            <h2 className="text-sm font-semibold text-foreground">{sk.firma.topPartners}</h2>
          </div>
          <div className="divide-y divide-border">
            {topPartners.map((p) => (
              <div key={p.ico} className="flex items-center justify-between px-4 py-2.5">
                <Link
                  to={`/firma/${p.ico}`}
                  className="text-sm text-primary underline-offset-2 hover:underline"
                >
                  {p.name}
                </Link>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {formatNumber(p.count)} zákazok
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
