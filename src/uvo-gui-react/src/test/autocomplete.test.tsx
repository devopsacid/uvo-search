import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderWithProviders, screen, fireEvent, waitFor } from './utils'
import { EntityAutocomplete } from '../components/search/EntityAutocomplete'
import { SearchPage } from '../pages/SearchPage'
import sk from '../i18n/sk'

let fetchCallCount = 0

global.fetch = vi.fn(async (input: RequestInfo | URL): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
  const urlObj = new URL(url, 'http://localhost')

  if (url.includes('/search/entities')) {
    const q = urlObj.searchParams.get('q')
    fetchCallCount++

    if (!q || q.length < 2) {
      return { ok: true, json: async () => ({ items: [] }) } as Response
    }

    return {
      ok: true,
      json: async () => ({
        items: [
          {
            ico: '87654321',
            name: `Supplier matching ${q}`,
            type: 'supplier',
            contract_count: 5,
            total_value: 5000,
          },
          {
            ico: '12345678',
            name: `Procurer matching ${q}`,
            type: 'procurer',
            contract_count: 10,
            total_value: 10000,
          },
        ],
      }),
    } as Response
  }

  if (url.includes('/contracts')) {
    return {
      ok: true,
      json: async () => ({
        data: [],
        pagination: { total: 0, limit: 20, offset: 0 },
      }),
    } as Response
  }

  return { ok: false, json: async () => ({}) } as Response
}) as typeof fetch

describe('Autocomplete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchCallCount = 0
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not fire request with less than 2 characters', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'a' } })

    vi.advanceTimersByTime(300)
    await waitFor(() => {
      expect(fetchCallCount).toBe(0)
    })
  })

  it('fires request when typing 2 or more characters', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'ab' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(fetchCallCount).toBeGreaterThan(0)
    })
  })

  it('waits 250ms before firing request (debounce)', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })

    fireEvent.change(input, { target: { value: 'a' } })
    fireEvent.change(input, { target: { value: 'ab' } })
    fireEvent.change(input, { target: { value: 'abc' } })

    vi.advanceTimersByTime(100)
    expect(fetchCallCount).toBe(0)

    vi.advanceTimersByTime(150)
    // After 250ms total, should fire
    await waitFor(() => {
      expect(fetchCallCount).toBeGreaterThan(0)
    })
  })

  it('shows dropdown when results are available', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })
  })

  it('displays supplier and procurer results with labels', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'match' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByText(/Supplier matching match/)).toBeInTheDocument()
      expect(screen.getByText(/Procurer matching match/)).toBeInTheDocument()
    })
  })

  it('displays type badges (Dod./Obst.)', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      const badges = screen.getAllByText(/Dod\.|Obst\./)
      expect(badges.length).toBeGreaterThan(0)
    })
  })

  it('arrow down moves selection to first item', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'ArrowDown' })

    await waitFor(() => {
      const option = screen.getAllByRole('option')[0]
      expect(option).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('arrow up and down navigate through options', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'ArrowDown' })

    await waitFor(() => {
      const options = screen.getAllByRole('option')
      expect(options[1]).toHaveAttribute('aria-selected', 'true')
    })

    fireEvent.keyDown(input, { key: 'ArrowUp' })

    await waitFor(() => {
      const options = screen.getAllByRole('option')
      expect(options[0]).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('Enter commits the selected item', async () => {
    const onSelect = vi.fn()
    renderWithProviders(<EntityAutocomplete onSelect={onSelect} />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'ArrowDown' })

    await waitFor(() => {
      const option = screen.getAllByRole('option')[0]
      expect(option).toHaveAttribute('aria-selected', 'true')
    })

    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith('87654321', 'supplier', 'Supplier matching test')
    })
  })

  it('Escape closes the dropdown', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'Escape' })

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  it('forwards / keydown to focus input globally', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })

    fireEvent.keyDown(document, { key: '/' })

    expect(input).toHaveFocus()
  })

  it('mouse click on option commits selection', async () => {
    const onSelect = vi.fn()
    renderWithProviders(<EntityAutocomplete onSelect={onSelect} />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    const firstOption = screen.getAllByRole('option')[0]
    fireEvent.mouseDown(firstOption)

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalled()
    })
  })

  it('without onSelect callback, Enter commits selection and clears input', async () => {
    renderWithProviders(<SearchPage />, { route: '/search' })

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder }) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })

    // On commit without onSelect, the component navigates and clears input
    await waitFor(() => {
      expect(input.value).toBe('')
    }, { timeout: 1000 })
  })

  it('clears input after commit', async () => {
    const onSelect = vi.fn()
    renderWithProviders(<EntityAutocomplete onSelect={onSelect} />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder }) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(input.value).toBe('')
    })
  })

  it('dropdown closes when input loses focus', async () => {
    renderWithProviders(<EntityAutocomplete />)

    const input = screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })
    fireEvent.change(input, { target: { value: 'test' } })

    vi.advanceTimersByTime(300)

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument()
    })

    fireEvent.blur(input)

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    }, { timeout: 500 })
  })

  it('does not show dropdown when input is empty', async () => {
    renderWithProviders(<EntityAutocomplete />)

    screen.getByRole('textbox', { name: sk.search.autocompletePlaceholder })

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
