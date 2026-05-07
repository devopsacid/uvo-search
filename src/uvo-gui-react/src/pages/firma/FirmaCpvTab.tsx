import { useParams } from 'react-router-dom'
import { useFirmaCpvProfile, type CpvProfileRow } from '@/api/queries/firma'
import { formatCurrency, formatNumber } from '@/lib/utils'
import sk from '@/i18n/sk'

function SkeletonCpvRows() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i} className="border-b border-border last:border-0">
          <td className="py-2 pr-4">
            <div className="h-4 w-20 animate-pulse rounded bg-muted" />
          </td>
          <td className="py-2 pr-4">
            <div className="h-4 w-40 animate-pulse rounded bg-muted" />
          </td>
          <td className="py-2 pr-4 w-32">
            <div className="h-2 w-full animate-pulse rounded-full bg-muted" />
          </td>
          <td className="py-2 pr-4 text-right">
            <div className="ml-auto h-4 w-24 animate-pulse rounded bg-muted" />
          </td>
          <td className="py-2 text-right">
            <div className="ml-auto h-4 w-8 animate-pulse rounded bg-muted" />
          </td>
        </tr>
      ))}
    </>
  )
}

function CpvBarTable({ rows }: { rows: CpvProfileRow[] }) {
  if (rows.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">{sk.firma.cpvNoData}</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            <th className="pb-2 pr-4 font-medium">CPV</th>
            <th className="pb-2 pr-4 font-medium">Kategória</th>
            <th className="pb-2 pr-4 w-32 font-medium">Podiel</th>
            <th className="pb-2 pr-4 text-right font-medium">Hodnota</th>
            <th className="pb-2 text-right font-medium">Zákazky</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code} className="border-b border-border last:border-0">
              <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">{row.code}</td>
              <td className="py-2 pr-4 max-w-xs">
                <span className="line-clamp-2">{row.label}</span>
              </td>
              <td className="py-2 pr-4 w-32">
                <div className="flex items-center gap-2">
                  <div className="h-2 flex-1 rounded-full bg-primary/20">
                    <div
                      className="h-2 rounded-full bg-primary"
                      style={{ width: `${Math.min(row.percentage, 100)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right tabular-nums text-xs text-muted-foreground">
                    {row.percentage.toFixed(1)}%
                  </span>
                </div>
              </td>
              <td className="py-2 pr-4 text-right tabular-nums">
                {formatCurrency(row.total_value)}
              </td>
              <td className="py-2 text-right tabular-nums">{formatNumber(row.contract_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function FirmaCpvTab() {
  const { ico } = useParams<{ ico: string }>()
  const safeIco = ico ?? ''

  const { data, isLoading, isError } = useFirmaCpvProfile(safeIco)

  return (
    <div className="space-y-4">
      <h2 className="text-base font-semibold text-foreground">{sk.firma.cpvTitle}</h2>

      {isError && (
        <p className="py-6 text-center text-sm text-muted-foreground">{sk.common.error}</p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Company section */}
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-foreground">{sk.firma.cpvCompany}</h3>
          {isLoading ? (
            <table className="w-full text-sm">
              <tbody>
                <SkeletonCpvRows />
              </tbody>
            </table>
          ) : (
            <CpvBarTable rows={data?.for_company ?? []} />
          )}
        </div>

        {/* Market baseline section */}
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-foreground">{sk.firma.cpvMarket}</h3>
          {isLoading ? (
            <table className="w-full text-sm">
              <tbody>
                <SkeletonCpvRows />
              </tbody>
            </table>
          ) : (
            <CpvBarTable rows={data?.market_baseline ?? []} />
          )}
        </div>
      </div>
    </div>
  )
}
