import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { App } from '../App'
import sk from '../i18n/sk'
import { makeAnalyticsFetch } from './fixtures/analytics'

// Stub fetch so TanStack Query doesn't hit the network; analytics endpoints return fixtures.
global.fetch = makeAnalyticsFetch().impl

describe('App', () => {
  it('renders the Slovak navigation label for analytics', async () => {
    render(<App />)
    const navItem = await screen.findByText(sk.nav.analytics)
    expect(navItem).toBeInTheDocument()
  })

  it('renders the Slovak navigation label for about', async () => {
    render(<App />)
    const navItem = await screen.findByText(sk.nav.about)
    expect(navItem).toBeInTheDocument()
  })
})
