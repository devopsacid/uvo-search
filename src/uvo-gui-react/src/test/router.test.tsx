import { describe, it, expect } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { render, waitFor } from '@testing-library/react'
import { legacyRedirects } from '@/router'

// Mounts only the redirect table (the exact array the app router spreads in),
// with a catch-all so the landing location can be inspected without lazy pages.
async function land(from: string) {
  const memoryRouter = createMemoryRouter(
    [...legacyRedirects, { path: '*', element: <div>landed</div> }],
    { initialEntries: [from] },
  )
  render(<RouterProvider router={memoryRouter} />)
  await waitFor(() => expect(memoryRouter.state.location.pathname).not.toBe(from.split(/[?#]/)[0]))
  return memoryRouter.state.location
}

const CASES: Array<[string, string]> = [
  ['/analytika', '/analytics/overview'],
  ['/analytika/prehlad', '/analytics/overview'],
  ['/analytika/koncentracia', '/analytics/concentration'],
  ['/analytika/cpv', '/analytics/cpv'],
  ['/analytika/pokrytie', '/analytics/coverage'],
  ['/firma/12345678', '/company/12345678/overview'],
  ['/firma/12345678/prehlad', '/company/12345678/overview'],
  ['/firma/12345678/zakazky', '/company/12345678/contracts'],
  ['/firma/12345678/siet', '/company/12345678/network'],
  ['/firma/12345678/partneri', '/company/12345678/partners'],
  ['/firma/12345678/cpv', '/company/12345678/cpv'],
  ['/firmy', '/companies'],
  ['/zakazky', '/contracts'],
  ['/hladaj', '/search'],
  ['/suppliers', '/companies'],
  ['/procurers', '/companies'],
  ['/pinpoint', '/companies'],
  ['/suppliers/12345678', '/company/12345678'],
  ['/procurers/12345678', '/company/12345678'],
  ['/cpv-trends', '/analytics/cpv'],
]

describe('legacy route redirects', () => {
  it.each(CASES)('%s -> %s and keeps ?query and #hash', async (from, to) => {
    const loc = await land(`${from}?x=1&cpv=45#frag`)
    expect(loc.pathname).toBe(to)
    expect(loc.search).toBe('?x=1&cpv=45')
    expect(loc.hash).toBe('#frag')
  })

  it('keeps the contracts drill-down params', async () => {
    const loc = await land('/zakazky?selected=abc&supplier_ico=36396567')
    expect(loc.pathname).toBe('/contracts')
    expect(new URLSearchParams(loc.search).get('selected')).toBe('abc')
    expect(new URLSearchParams(loc.search).get('supplier_ico')).toBe('36396567')
  })
})
