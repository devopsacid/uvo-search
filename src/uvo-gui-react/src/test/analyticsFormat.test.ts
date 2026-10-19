import { describe, it, expect } from 'vitest'
import { formatCompactCurrency, formatPercent } from '@/lib/utils'

describe('formatPercent', () => {
  it('uses one decimal, decimal comma and a narrow no-break space', () => {
    expect(formatPercent(12.34)).toBe('12,3 %')
    expect(formatPercent(0)).toBe('0,0 %')
    expect(formatPercent(100)).toBe('100,0 %')
  })

  it('keeps the sign for negative values', () => {
    expect(formatPercent(-4.56)).toBe('-4,6 %')
  })
})

describe('formatCompactCurrency', () => {
  it('scales to thousands, millions and billions with a euro sign', () => {
    expect(formatCompactCurrency(950)).toBe('950 €')
    expect(formatCompactCurrency(15_000)).toBe('15 tis. €')
    expect(formatCompactCurrency(1_234_567)).toBe('1,2 M €')
    expect(formatCompactCurrency(4_200_000_000)).toBe('4,2 mld. €')
  })
})
