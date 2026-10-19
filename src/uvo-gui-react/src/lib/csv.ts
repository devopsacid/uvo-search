/**
 * Client-side CSV for Slovak spreadsheets (spec §5.7): UTF-8 BOM, `;` delimiter,
 * decimal comma, CRLF line endings.
 */

export interface CsvColumn<T> {
  header: string
  value: (row: T) => string | number | null | undefined
}

const BOM = '﻿'
const DELIMITER = ';'
const EOL = '\r\n'
// Spreadsheet formula triggers; a leading apostrophe makes the cell inert text.
const FORMULA_START = /^[=+\-@\t\r]/

export function roundCsvNumber(n: number, decimals = 2): number {
  const factor = 10 ** decimals
  const rounded = Math.round((n + Number.EPSILON * Math.sign(n)) * factor) / factor
  return Object.is(rounded, -0) ? 0 : rounded
}

function formatCell(raw: string | number | null | undefined): string {
  if (raw === null || raw === undefined) return ''
  let text: string
  if (typeof raw === 'number') {
    // Round away float noise (1009305.2540000001); 2 decimals covers EUR amounts and % shares.
    text = Number.isFinite(raw) ? String(roundCsvNumber(raw)).replace('.', ',') : ''
  } else {
    text = FORMULA_START.test(raw) ? `'${raw}` : raw
  }
  return /[";\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv<T>(rows: readonly T[], columns: readonly CsvColumn<T>[]): string {
  const lines = [columns.map((c) => formatCell(c.header)).join(DELIMITER)]
  for (const row of rows) {
    lines.push(columns.map((c) => formatCell(c.value(row))).join(DELIMITER))
  }
  return BOM + lines.join(EOL) + EOL
}

/** `uvo-<view>-<date_from>_<date_to>.csv` */
export function csvFilename(view: string, dateFrom: string, dateTo: string): string {
  return `uvo-${view}-${dateFrom}_${dateTo}.csv`
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
