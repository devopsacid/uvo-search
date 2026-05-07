import { Link, useParams } from 'react-router-dom'
import { useProcurerConcentration } from '@/api/queries/procurers'
import { DonutChart, type DonutSlice } from '@/components/charts/DonutChart'
import { Gauge } from '@/components/charts/Gauge'
import { Skeleton } from '@/components/ui/Skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { EntityLink } from '@/components/entity/EntityLink'
import { formatCurrency } from '@/lib/utils'
import sk from '@/i18n/sk'

function hhiRisk(hhi: number): { label: string; cls: 'low' | 'medium' | 'high' } {
  if (hhi < 1500) return { label: sk.concentration.hhiLow, cls: 'low' }
  if (hhi < 2500) return { label: sk.concentration.hhiMedium, cls: 'medium' }
  return { label: sk.concentration.hhiHigh, cls: 'high' }
}

export function ConcentrationPage() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data, isLoading, isError } = useProcurerConcentration(safeIco, 10)

  if (isError) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">{sk.common.error}</p>
        <Link to="/firmy" className="mt-4 block text-sm text-primary hover:underline">
          {sk.common.back}
        </Link>
      </div>
    )
  }

  const risk = data ? hhiRisk(data.hhi) : null

  const donutData: DonutSlice[] = (data?.top_suppliers ?? []).map((s) => ({
    name: s.name || s.ico,
    value: s.share,
    id: s.ico,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          {isLoading ? (
            <Skeleton className="h-7 w-64" />
          ) : (
            <>
              <h1 className="text-xl font-semibold text-foreground">{sk.concentration.title}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {data?.procurer_name} &middot; {safeIco}
              </p>
            </>
          )}
        </div>
        <Link
          to={`/firma/${safeIco}`}
          className="text-sm text-muted-foreground hover:text-foreground hover:underline"
        >
          ← {sk.common.back}
        </Link>
      </div>

      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !data || data.top_suppliers.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">{sk.concentration.noData}</p>
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          {/* Donut */}
          <div className="rounded-lg border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">
              {sk.concentration.shareLabel}
            </h2>
            <DonutChart
              data={donutData}
              valueFormatter={(v) => `${v.toFixed(1)}%`}
            />
          </div>

          {/* HHI gauge */}
          <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-semibold text-foreground">{sk.concentration.hhi}</h2>
            {risk && (
              <Gauge
                value={data.hhi}
                label={sk.concentration.hhi}
                riskLabel={risk.label}
                riskClass={risk.cls}
              />
            )}
          </div>
        </div>
      )}

      {/* Top suppliers table */}
      {!isLoading && (data?.top_suppliers.length ?? 0) > 0 && (
        <div className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">{sk.concentration.topSuppliersTitle}</h2>
          </div>
          <Table>
            <TableHeader>
              <tr>
                <TableHead>{sk.concentration.colSupplier}</TableHead>
                <TableHead className="text-right">{sk.concentration.colValue}</TableHead>
                <TableHead className="text-right">{sk.concentration.colShare}</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              {data!.top_suppliers.map((s) => (
                <TableRow key={s.ico}>
                  <TableCell>
                    <EntityLink ico={s.ico} name={s.name} type="supplier" />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCurrency(s.total_value)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{s.share.toFixed(1)}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
