/// <reference types="vite/client" />
import { describe, it, expect } from 'vitest'

// Every user-facing Slovak string lives in src/i18n/sk.ts. Slovak diacritics in a
// .tsx file (outside comments) almost always mean a hard-coded UI string.
const SLOVAK_DIACRITICS = /[áäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]/

const sources = import.meta.glob('/src/**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('i18n guard', () => {
  it('scans the component sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(10)
  })

  it('keeps Slovak diacritics out of .tsx outside tests', () => {
    const offenders: string[] = []
    for (const [file, code] of Object.entries(sources)) {
      if (file.includes('/src/test/')) continue
      stripComments(code)
        .split('\n')
        .forEach((line, i) => {
          if (SLOVAK_DIACRITICS.test(line)) offenders.push(`${file}:${i + 1}: ${line.trim()}`)
        })
    }
    expect(offenders).toEqual([])
  })
})
