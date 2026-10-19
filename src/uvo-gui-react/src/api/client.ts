import type { ApiError } from './types'

const BASE_URL = '/api'

class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'HttpError'
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      message = body.detail ?? message
    } catch {
      // ignore parse error — use status text
    }
    throw new HttpError(response.status, message)
  }

  return response.json() as Promise<T>
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof HttpError
}

export interface RequestOptions {
  /** Pass the AbortSignal from the TanStack Query queryFn context so superseded requests are cancelled. */
  signal?: AbortSignal
}

export const apiClient = {
  get: <T>(path: string, options: RequestOptions = {}) =>
    apiFetch<T>(path, { signal: options.signal }),
}
