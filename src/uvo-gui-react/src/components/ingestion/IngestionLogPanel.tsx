import { useState } from 'react'
import { useIngestionLog } from '@/api/queries/ingestionLog'
import type { IngestionLogLevel } from '@/api/types'
import sk from '@/i18n/sk'
import { cn } from '@/lib/utils'

const LEVELS: Array<{ key: IngestionLogLevel | 'all'; label: string }> = [
  { key: 'all', label: sk.ingestionLog.levelAll },
  { key: 'info', label: sk.ingestionLog.levelInfo },
  { key: 'warning', label: sk.ingestionLog.levelWarning },
  { key: 'error', label: sk.ingestionLog.levelError },
]

const SOURCES = ['vestnik', 'crz', 'ted', 'itms'] as const

const EVENTS = [
  'worker_started',
  'worker_stopped',
  'cycle_complete',
  'cycle_failed',
  'batch_written',
  'decode_failed',
  'write_failed',
  'redis_connect_failed',
  'notice_invalid_date',
  'validation_summary',
] as const

const LEVEL_CLASSES: Record<IngestionLogLevel, string> = {
  info: 'text-slate-600',
  warning: 'text-amber-600',
  error: 'text-red-600',
  critical: 'text-red-700 font-semibold',
}

function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('sk-SK', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(iso))
}

export function IngestionLogPanel() {
  const [level, setLevel] = useState<IngestionLogLevel | 'all'>('all')
  const [source, setSource] = useState<string>('')
  const [event, setEvent] = useState<string>('')

  const { data, isLoading, isError } = useIngestionLog({
    level: level === 'all' ? undefined : level,
    source: source || undefined,
    event: event || undefined,
    limit: 50,
  })

  return (
    <section className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-3 justify-between">
        <h2 className="text-lg font-semibold">{sk.ingestionLog.title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-2">
            {LEVELS.map((l) => (
              <button
                key={l.key}
                onClick={() => setLevel(l.key as IngestionLogLevel | 'all')}
                className={cn(
                  'rounded border px-2 py-1 text-sm',
                  level === l.key
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-slate-200 text-slate-600',
                )}
              >
                {l.label}
              </button>
            ))}
          </div>
          <select
            aria-label={sk.ingestionLog.filterSource}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="rounded border border-slate-200 px-2 py-1 text-sm text-slate-600"
          >
            <option value="">{sk.ingestionLog.sourceAll}</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            aria-label={sk.ingestionLog.filterEvent}
            value={event}
            onChange={(e) => setEvent(e.target.value)}
            className="rounded border border-slate-200 px-2 py-1 text-sm text-slate-600"
          >
            <option value="">{sk.ingestionLog.eventAll}</option>
            {EVENTS.map((ev) => (
              <option key={ev} value={ev}>{ev}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading && <div className="text-sm text-slate-500">{sk.ingestionLog.loading}</div>}
      {isError && <div className="text-sm text-red-600">{sk.common.error}</div>}
      {data && Array.isArray(data.items) && data.items.length === 0 && (
        <div className="text-sm text-slate-500">{sk.ingestionLog.empty}</div>
      )}

      {data && Array.isArray(data.items) && data.items.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="py-1 pr-2">{sk.ingestionLog.colTime}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colLevel}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colEvent}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colSource}</th>
              <th className="py-1 pr-2">{sk.ingestionLog.colMessage}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((it, i) => (
              <tr key={i} className="border-t border-slate-100 align-top">
                <td className="py-1 pr-2 whitespace-nowrap text-slate-600">
                  {formatTime(it.ts)}
                </td>
                <td className={cn('py-1 pr-2', LEVEL_CLASSES[it.level])}>{it.level}</td>
                <td className="py-1 pr-2 font-mono text-xs">{it.event}</td>
                <td className="py-1 pr-2">{it.source ?? '—'}</td>
                <td className="py-1 pr-2">{it.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
