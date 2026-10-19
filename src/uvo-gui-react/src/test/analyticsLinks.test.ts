import { describe, it, expect } from 'vitest'
import {
  activePreset,
  defaultRange,
  filtersToParams,
  isDefaultFilters,
  periodRange,
  presetRange,
  resolveFilters,
  validateRange,
} from '@/lib/analyticsFilters'
import { analyticsLink, firmaLink, zakazkyLink, zakazkyPeriodLink } from '@/lib/analyticsLinks'

const TODAY = new Date(2026, 9, 19) // 2026-10-19

describe('filter defaults and presets', () => {
  it('defaults to Jan 1 of (year - 4) until today', () => {
    expect(defaultRange(TODAY)).toEqual({ date_from: '2022-01-01', date_to: '2026-10-19' })
  })

  it('computes each preset', () => {
    expect(presetRange('thisYear', TODAY)).toEqual({ date_from: '2026-01-01', date_to: '2026-10-19' })
    expect(presetRange('lastYear', TODAY)).toEqual({ date_from: '2025-01-01', date_to: '2025-12-31' })
    expect(presetRange('last5', TODAY)).toEqual(defaultRange(TODAY))
    expect(presetRange('all', TODAY)).toEqual({ date_from: '2014-01-01', date_to: '2026-10-19' })
  })

  it('detects the active preset', () => {
    expect(activePreset(resolveFilters(new URLSearchParams(), TODAY), TODAY)).toBe('last5')
    expect(
      activePreset(resolveFilters(new URLSearchParams('date_from=2025-01-01&date_to=2025-12-31'), TODAY), TODAY),
    ).toBe('lastYear')
    expect(
      activePreset(resolveFilters(new URLSearchParams('date_from=2023-02-01&date_to=2023-03-01'), TODAY), TODAY),
    ).toBeNull()
  })
})

describe('resolveFilters', () => {
  it('applies defaults in memory and reads valid params', () => {
    const f = resolveFilters(new URLSearchParams('cpv=45&source=crz&procurer_ico=123&supplier_ico=456'), TODAY)
    expect(f).toEqual({
      date_from: '2022-01-01',
      date_to: '2026-10-19',
      cpv: '45',
      source: 'crz',
      procurer_ico: '123',
      supplier_ico: '456',
    })
  })

  it('drops invalid values instead of sending them to the API', () => {
    const f = resolveFilters(
      new URLSearchParams('cpv=x&source=nope&procurer_ico=12ab&date_from=yesterday'),
      TODAY,
    )
    expect(f.cpv).toBeUndefined()
    expect(f.source).toBeUndefined()
    expect(f.procurer_ico).toBeUndefined()
    expect(f.date_from).toBe('2022-01-01')
  })

  it('knows when nothing deviates from the defaults', () => {
    expect(isDefaultFilters(resolveFilters(new URLSearchParams(), TODAY), TODAY)).toBe(true)
    expect(isDefaultFilters(resolveFilters(new URLSearchParams('cpv=45'), TODAY), TODAY)).toBe(false)
  })
})

describe('validateRange', () => {
  it('flags reversed and over-long ranges', () => {
    expect(validateRange({ date_from: '2024-01-01', date_to: '2023-01-01' })).toBe('reversed')
    expect(validateRange({ date_from: '2010-01-01', date_to: '2026-01-02' })).toBe('span')
    expect(validateRange({ date_from: '2011-01-01', date_to: '2026-01-01' })).toBeNull()
  })
})

describe('periodRange', () => {
  it('expands year, quarter and month buckets', () => {
    expect(periodRange('2024')).toEqual({ date_from: '2024-01-01', date_to: '2024-12-31' })
    expect(periodRange('2024-Q2')).toEqual({ date_from: '2024-04-01', date_to: '2024-06-30' })
    expect(periodRange('2024-02')).toEqual({ date_from: '2024-02-01', date_to: '2024-02-29' })
    expect(periodRange('nonsense')).toBeNull()
  })
})

describe('links', () => {
  const filters = resolveFilters(new URLSearchParams('cpv=45&source=vestnik'), TODAY)

  it('zakazkyLink copies the effective filters and adds the clicked entity', () => {
    const href = zakazkyLink(filters, { supplier_ico: '36396567' })
    const url = new URL(href, 'http://x')
    expect(url.pathname).toBe('/zakazky')
    expect(url.searchParams.get('date_from')).toBe('2022-01-01')
    expect(url.searchParams.get('date_to')).toBe('2026-10-19')
    expect(url.searchParams.get('cpv')).toBe('45')
    expect(url.searchParams.get('source')).toBe('vestnik')
    expect(url.searchParams.get('supplier_ico')).toBe('36396567')
  })

  it('extra overrides and can remove a filter', () => {
    const href = zakazkyLink(filters, { cpv: '71', source: undefined })
    const url = new URL(href, 'http://x')
    expect(url.searchParams.get('cpv')).toBe('71')
    expect(url.searchParams.has('source')).toBe(false)
  })

  it('zakazkyPeriodLink narrows the dates to the bucket', () => {
    const url = new URL(zakazkyPeriodLink(filters, '2024-Q1'), 'http://x')
    expect(url.searchParams.get('date_from')).toBe('2024-01-01')
    expect(url.searchParams.get('date_to')).toBe('2024-03-31')
  })

  it('firmaLink and analyticsLink', () => {
    expect(firmaLink('123')).toBe('/firma/123')
    expect(analyticsLink('prehlad', { procurer_ico: '123' })).toBe('/analytika/prehlad?procurer_ico=123')
    expect(analyticsLink('cpv')).toBe('/analytika/cpv')
  })

  it('filtersToParams skips unset values', () => {
    expect(filtersToParams({ date_from: 'a', date_to: 'b' }).toString()).toBe('date_from=a&date_to=b')
  })
})
