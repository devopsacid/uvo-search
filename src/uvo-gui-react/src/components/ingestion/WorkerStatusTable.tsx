import { useWorkerStatus } from '@/api/queries/workerStatus'
import type { WorkerStatusValue } from '@/api/types'
import sk from '@/i18n/sk'
import { cn } from '@/lib/utils'

const NAME: Record<string, string> = {
  'extractor:vestnik': 'Vestník extraktor',
  'extractor:crz': 'CRZ extraktor',
  'extractor:ted': 'TED extraktor',
  'extractor:itms': 'ITMS extraktor',
  'ingestor': 'Ingestor',
  'dedup-worker': 'Dedup worker',
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return '—'
  const mins = Math.floor(seconds / 60)
  const hours = Math.floor(mins / 60)
  const days = Math.floor(hours / 24)
  if (days >= 2) return `pred ${days} dňami`
  if (days === 1) return `pred 1 dňom`
  if (hours >= 1) {
    const remMins = mins % 60
    return remMins > 0 ? `pred ${hours} h ${remMins} min` : `pred ${hours} h`
  }
  if (mins >= 1) return `pred ${mins} min`
  return 'práve teraz'
}

function statusLabel(status: WorkerStatusValue): string {
  switch (status) {
    case 'healthy': return sk.workerStatus.statusHealthy
    case 'stale':   return sk.workerStatus.statusStale
    case 'stopped': return sk.workerStatus.statusStopped
    case 'error':   return sk.workerStatus.statusError
    case 'unknown': return sk.workerStatus.statusUnknown
  }
}

function statusBadgeClass(status: WorkerStatusValue): string {
  switch (status) {
    case 'healthy': return 'bg-green-100 text-green-800'
    case 'stale':   return 'bg-amber-100 text-amber-800'
    case 'stopped': return 'bg-slate-100 text-slate-600'
    case 'error':   return 'bg-red-100 text-red-800'
    case 'unknown': return 'bg-slate-100 text-slate-500'
  }
}

export function WorkerStatusTable() {
  const { data, isLoading } = useWorkerStatus()

  return (
    <section className="rounded-lg border bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-lg font-semibold">{sk.workerStatus.title}</h2>

      {isLoading && (
        <div className="text-sm text-slate-500">{sk.workerStatus.loading}</div>
      )}

      {data && (data.workers ?? []).length === 0 && (
        <div className="text-sm text-slate-500">{sk.workerStatus.empty}</div>
      )}

      {data && (data.workers ?? []).length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-4">{sk.workerStatus.colService}</th>
                <th className="py-1 pr-4">{sk.workerStatus.colLastEvent}</th>
                <th className="py-1 pr-4">{sk.workerStatus.colAge}</th>
                <th className="py-1">{sk.workerStatus.colStatus}</th>
              </tr>
            </thead>
            <tbody>
              {(data.workers ?? []).map((w) => (
                <tr key={w.component} className="border-t border-slate-100">
                  <td className="py-1.5 pr-4 font-medium">
                    {NAME[w.component] ?? w.component}
                  </td>
                  <td className="py-1.5 pr-4 font-mono text-xs text-slate-600">
                    {w.last_event ?? '—'}
                  </td>
                  <td className="py-1.5 pr-4 text-slate-500">
                    {formatAge(w.age_seconds)}
                  </td>
                  <td className="py-1.5">
                    <span
                      data-testid={`worker-status-badge-${w.component}`}
                      className={cn(
                        'inline-block rounded px-2 py-0.5 text-xs font-medium',
                        statusBadgeClass(w.status),
                      )}
                    >
                      {statusLabel(w.status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
