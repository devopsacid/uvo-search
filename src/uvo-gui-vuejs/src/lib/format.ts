export function fmtValue(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  if (abs >= 1_000_000_000) return `€${(v / 1_000_000_000).toFixed(2)}B`
  if (abs >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `€${(v / 1_000).toFixed(0)}K`
  return `€${v.toFixed(0)}`
}

export function fmtInt(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US').replace(/,/g, ',')
}

export function fmtPct(v: number, digits = 1): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(digits)}%`
}

export function fmtTs(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
