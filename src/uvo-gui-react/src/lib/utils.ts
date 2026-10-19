import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import sk from '@/i18n/sk'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('sk-SK', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('sk-SK').format(value)
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  const units = ['kB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit++
  }
  return `${new Intl.NumberFormat('sk-SK', {
    minimumFractionDigits: size < 10 ? 1 : 0,
    maximumFractionDigits: size < 10 ? 1 : 0,
  }).format(size)} ${units[unit]}`
}

const DASH = '—'

export function formatDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString('sk-SK') : DASH
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat('sk-SK', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

/** Log timestamps: day, month and time with seconds. */
export function formatLogTime(iso: string): string {
  return new Intl.DateTimeFormat('sk-SK', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(iso))
}

/** "2026-03-28" -> "28.03." */
export function formatShortDate(isoDate: string): string {
  const [, month, day] = isoDate.split('-')
  return `${day}.${month}.`
}

/** Compact amount for chart axes and tiles: 1.2 M, 15 tis. */
export function formatMillions(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} ${sk.common.millionsAbbrev}`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)} ${sk.common.thousandsAbbrev}`
  return String(value)
}

/** Relative age in Slovak; `never` is shown when seconds is null. */
export function formatAge(seconds: number | null, never: string = DASH): string {
  if (seconds === null) return never
  const m = Math.floor(seconds / 60)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  const c = sk.common
  if (d >= 2) return c.agoDays.replace('{n}', String(d))
  if (d === 1) return c.agoOneDay
  if (h >= 1) {
    const rem = m % 60
    return (rem > 0 ? c.agoHoursMinutes : c.agoHours).replace('{h}', String(h)).replace('{m}', String(rem))
  }
  if (m >= 1) return c.agoMinutes.replace('{m}', String(m))
  return c.agoNow
}
