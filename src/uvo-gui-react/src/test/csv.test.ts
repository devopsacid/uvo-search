import { describe, it, expect, vi, afterEach } from 'vitest'
import { csvFilename, downloadCsv, toCsv } from '@/lib/csv'

interface Row {
  name: string
  value: number | null
}

const columns = [
  { header: 'Názov', value: (r: Row) => r.name },
  { header: 'Hodnota', value: (r: Row) => r.value },
]

describe('toCsv', () => {
  it('starts with a UTF-8 BOM, uses ; and CRLF', () => {
    const csv = toCsv([{ name: 'A', value: 1 }], columns)
    expect(csv.charCodeAt(0)).toBe(0xfeff)
    expect(csv).toBe('﻿Názov;Hodnota\r\nA;1\r\n')
  })

  it('writes a decimal comma for fractional numbers', () => {
    const csv = toCsv([{ name: 'A', value: 12.5 }], columns)
    expect(csv).toContain('A;12,5\r\n')
  })

  it('leaves null cells empty', () => {
    expect(toCsv([{ name: 'A', value: null }], columns)).toContain('A;\r\n')
  })

  it('quotes cells containing the delimiter, quotes or newlines', () => {
    const csv = toCsv([{ name: 'a;b "c"\nd', value: 1 }], columns)
    expect(csv).toContain('"a;b ""c""\nd";1')
  })

  it('neutralises spreadsheet formulas in text cells', () => {
    const csv = toCsv([{ name: '=HYPERLINK("x")', value: -3 }], columns)
    expect(csv).toContain(`"'=HYPERLINK(""x"")";-3`)
  })

  it('emits only the header for an empty dataset', () => {
    expect(toCsv([], columns)).toBe('﻿Názov;Hodnota\r\n')
  })
})

describe('csvFilename', () => {
  it('follows uvo-<view>-<from>_<to>.csv', () => {
    expect(csvFilename('top-suppliers', '2022-01-01', '2026-10-19')).toBe(
      'uvo-top-suppliers-2022-01-01_2026-10-19.csv',
    )
  })
})

describe('downloadCsv', () => {
  afterEach(() => vi.restoreAllMocks())

  it('creates a blob link, clicks it and revokes the url', () => {
    const create = vi.fn(() => 'blob:x')
    const revoke = vi.fn()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    downloadCsv('a.csv', 'x')
    expect(create).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalledTimes(1)
    expect(revoke).toHaveBeenCalledWith('blob:x')
  })
})

describe('toCsv number rounding', () => {
  it('rounds float noise to 2 decimals, keeping the decimal comma', () => {
    expect(toCsv([{ name: 'A', value: 1009305.2540000001 }], columns)).toContain('A;1009305,25\r\n')
    expect(toCsv([{ name: 'A', value: 0.1 + 0.2 }], columns)).toContain('A;0,3\r\n')
    expect(toCsv([{ name: 'A', value: 12.5 }], columns)).toContain('A;12,5\r\n')
    expect(toCsv([{ name: 'A', value: 42 }], columns)).toContain('A;42\r\n')
    expect(toCsv([{ name: 'A', value: -0.001 }], columns)).toContain('A;0\r\n')
  })
})
