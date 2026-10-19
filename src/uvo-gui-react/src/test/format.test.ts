import { describe, it, expect } from 'vitest'
import { formatAge, formatDate, formatMillions, formatShortDate } from '@/lib/utils'

describe('formatAge', () => {
  it('uses the fallback for null', () => {
    expect(formatAge(null)).toBe('—')
    expect(formatAge(null, 'Nikdy')).toBe('Nikdy')
  })
  it('formats each magnitude in Slovak', () => {
    expect(formatAge(5)).toBe('práve teraz')
    expect(formatAge(5 * 60)).toBe('pred 5 min')
    expect(formatAge(3600)).toBe('pred 1 h')
    expect(formatAge(3600 + 120)).toBe('pred 1 h 2 min')
    expect(formatAge(86400)).toBe('pred 1 dňom')
    expect(formatAge(3 * 86400)).toBe('pred 3 dňami')
  })
})

describe('date and amount helpers', () => {
  it('formatDate handles empty input', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('2026-03-28')).toMatch(/28/)
  })
  it('formatShortDate drops the year', () => {
    expect(formatShortDate('2026-03-28')).toBe('28.03.')
  })
  it('formatMillions abbreviates', () => {
    expect(formatMillions(2_500_000)).toBe('2.5 M')
    expect(formatMillions(15_000)).toBe('15 tis.')
    expect(formatMillions(900)).toBe('900')
  })
})
