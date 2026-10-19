/**
 * Pure helpers for the analytics filter model (spec §5.1 / §4.3): defaults, presets,
 * parsing from URL params and validation. No React in here so it is trivially testable.
 */

import type { AnalyticsGranularity } from '@/api/types'
import { fillTemplate, formatDate } from '@/lib/utils'
import sk from '@/i18n/sk'

export interface AnalyticsFilters {
  /** ISO date, always set (default or from the URL). */
  date_from: string
  /** ISO date, always set (default or from the URL). */
  date_to: string
  cpv?: string
  source?: string
  procurer_ico?: string
  supplier_ico?: string
}

export const OPTIONAL_FILTER_KEYS = ['cpv', 'source', 'procurer_ico', 'supplier_ico'] as const
export const FILTER_KEYS = ['date_from', 'date_to', ...OPTIONAL_FILTER_KEYS] as const
export type FilterKey = (typeof FILTER_KEYS)[number]

export const SOURCES = ['vestnik', 'crz', 'ted', 'uvo', 'itms'] as const

/** First year with data for the "Všetko" preset. */
export const ALL_SINCE = '2014-01-01'
/** Server-side limit (spec §4.3). */
export const MAX_SPAN_YEARS = 15

export type PresetId = 'thisYear' | 'lastYear' | 'last5' | 'all'
export const PRESET_IDS: PresetId[] = ['thisYear', 'lastYear', 'last5', 'all']

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** Local-calendar YYYY-MM-DD (not UTC, so "today" matches what the user sees). */
export function isoDate(d: Date): string {
  const y = String(d.getFullYear()).padStart(4, '0')
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function defaultRange(today: Date = new Date()): { date_from: string; date_to: string } {
  return { date_from: `${today.getFullYear() - 4}-01-01`, date_to: isoDate(today) }
}

export function presetRange(id: PresetId, today: Date = new Date()): { date_from: string; date_to: string } {
  const y = today.getFullYear()
  switch (id) {
    case 'thisYear':
      return { date_from: `${y}-01-01`, date_to: isoDate(today) }
    case 'lastYear':
      return { date_from: `${y - 1}-01-01`, date_to: `${y - 1}-12-31` }
    case 'last5':
      return defaultRange(today)
    case 'all':
      return { date_from: ALL_SINCE, date_to: isoDate(today) }
  }
}

export function activePreset(f: AnalyticsFilters, today: Date = new Date()): PresetId | null {
  for (const id of PRESET_IDS) {
    const r = presetRange(id, today)
    if (r.date_from === f.date_from && r.date_to === f.date_to) return id
  }
  return null
}

function cleanDigits(raw: string | null, min: number, max: number): string | undefined {
  if (!raw) return undefined
  return new RegExp(`^\\d{${min},${max}}$`).test(raw) ? raw : undefined
}

/** Read the effective filters (defaults applied) from URL params. Garbage values fall back to "unset". */
export function resolveFilters(params: URLSearchParams, today: Date = new Date()): AnalyticsFilters {
  const def = defaultRange(today)
  const from = params.get('date_from')
  const to = params.get('date_to')
  const source = params.get('source')
  return {
    date_from: from && ISO_DATE.test(from) ? from : def.date_from,
    date_to: to && ISO_DATE.test(to) ? to : def.date_to,
    cpv: cleanDigits(params.get('cpv'), 2, 8),
    source: source && (SOURCES as readonly string[]).includes(source) ? source : undefined,
    procurer_ico: cleanDigits(params.get('procurer_ico'), 1, 12),
    supplier_ico: cleanDigits(params.get('supplier_ico'), 1, 12),
  }
}

export type RangeProblem = 'reversed' | 'span'

/** Mirror of the server rule (422 otherwise): from <= to and span <= 15 years. */
export function validateRange(f: Pick<AnalyticsFilters, 'date_from' | 'date_to'>): RangeProblem | null {
  if (f.date_from > f.date_to) return 'reversed'
  const from = new Date(`${f.date_from}T00:00:00`)
  const limit = new Date(from)
  limit.setFullYear(limit.getFullYear() + MAX_SPAN_YEARS)
  if (new Date(`${f.date_to}T00:00:00`) > limit) return 'span'
  return null
}

/** True when nothing differs from the defaults (no optional filter, default range). */
export function isDefaultFilters(f: AnalyticsFilters, today: Date = new Date()): boolean {
  const def = defaultRange(today)
  return (
    f.date_from === def.date_from &&
    f.date_to === def.date_to &&
    OPTIONAL_FILTER_KEYS.every((k) => !f[k])
  )
}

/** Query-string params for an analytics endpoint or a drill-down link (set values only). */
export function filtersToParams(f: AnalyticsFilters, extra: Partial<Record<string, string | undefined>> = {}): URLSearchParams {
  const params = new URLSearchParams()
  const merged: Record<string, string | undefined> = { ...f, ...extra }
  for (const key of FILTER_KEYS) {
    const v = merged[key]
    if (v) params.set(key, v)
  }
  for (const [key, v] of Object.entries(extra)) {
    if (!(FILTER_KEYS as readonly string[]).includes(key) && v) params.set(key, v)
  }
  return params
}

/** Bucket label from the API ("2024-03", "2024-Q1", "2024") to an inclusive date range. */
export function periodRange(period: string): { date_from: string; date_to: string } | null {
  let m = /^(\d{4})$/.exec(period)
  if (m) return { date_from: `${m[1]}-01-01`, date_to: `${m[1]}-12-31` }
  m = /^(\d{4})-Q([1-4])$/.exec(period)
  if (m) {
    const startMonth = (Number(m[2]) - 1) * 3 + 1
    const endMonth = startMonth + 2
    return {
      date_from: `${m[1]}-${String(startMonth).padStart(2, '0')}-01`,
      date_to: `${m[1]}-${String(endMonth).padStart(2, '0')}-${lastDay(Number(m[1]), endMonth)}`,
    }
  }
  m = /^(\d{4})-(\d{2})$/.exec(period)
  if (m) {
    return {
      date_from: `${m[1]}-${m[2]}-01`,
      date_to: `${m[1]}-${m[2]}-${lastDay(Number(m[1]), Number(m[2]))}`,
    }
  }
  return null
}

/** Axis / table label for an API bucket: "2024" -> "2024", "2024-Q1" -> "Q1 2024", "2024-03" -> "03/2024". */
export function formatPeriodLabel(period: string): string {
  let m = /^(\d{4})-Q([1-4])$/.exec(period)
  if (m) return `Q${m[2]} ${m[1]}`
  m = /^(\d{4})-(\d{2})$/.exec(period)
  if (m) return `${m[2]}/${m[1]}`
  return period
}

function lastDay(year: number, month: number): string {
  return String(new Date(year, month, 0).getDate()).padStart(2, '0')
}

/** "Obdobie: 1. 1. 2022 – 19. 10. 2026" caption used under every chart title. */
export function periodCaption(f: Pick<AnalyticsFilters, 'date_from' | 'date_to'>): string {
  return fillTemplate(sk.analytics.charts.period, { from: formatDate(f.date_from), to: formatDate(f.date_to) })
}

/** Spec §5.2: months when the span is at most 3 years, years otherwise. */
export function autoGranularity(f: Pick<AnalyticsFilters, 'date_from' | 'date_to'>): AnalyticsGranularity {
  const from = new Date(`${f.date_from}T00:00:00`)
  const limit = new Date(from)
  limit.setFullYear(limit.getFullYear() + 3)
  return new Date(`${f.date_to}T00:00:00`) <= limit ? 'month' : 'year'
}
