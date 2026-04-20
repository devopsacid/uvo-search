import { ReactElement } from 'react'
import { render, RenderOptions, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  route?: string
  /** When provided, wraps ui in a Routes/Route so useParams() resolves correctly. */
  routePattern?: string
  queryClient?: QueryClient
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    routePattern,
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
        },
      },
    }),
    ...renderOptions
  }: RenderWithProvidersOptions = {},
) {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        {routePattern ? (
          <Routes>
            <Route path={routePattern} element={children} />
          </Routes>
        ) : (
          children
        )}
      </MemoryRouter>
    </QueryClientProvider>
  )

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  }
}

export function setupFetch(
  responses: Record<string, { status?: number; body: unknown }>,
) {
  global.fetch = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    const path = new URL(url, 'http://localhost').pathname + new URL(url, 'http://localhost').search
    const key = Object.keys(responses).find((k) => path.includes(k)) || Object.keys(responses)[0]
    const response = responses[key]

    if (!response) {
      return {
        ok: false,
        status: 404,
        json: async () => ({ message: 'Not found' }),
      } as Response
    }

    return {
      ok: (response.status ?? 200) < 400,
      status: response.status ?? 200,
      json: async () => response.body,
    } as Response
  }) as typeof fetch

  return () => {
    vi.restoreAllMocks()
  }
}

export { screen, fireEvent, within, waitFor }
