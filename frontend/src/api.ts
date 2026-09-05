export type Stage = 'uninitialized' | 'initial' | 'expanded' | 'synchronized' | 'contracted'

export interface DemoStatus {
  stage: Stage
  revision: string | null
  v1_available: boolean
  v2_available: boolean
  v1_retired: boolean
  next_stage: Stage | null
  can_migrate: boolean
  can_retire_v1: boolean
  controls_enabled: boolean
}

export interface LegacyUser { name: string }
export interface ModernUser { first_name: string; last_name: string }
export type Version = 'v1' | 'v2'

export class ApiError extends Error {
  constructor(message: string, public status: number | null, public response?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

function errorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object' || !('detail' in body)) return fallback
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item: { loc?: string[]; msg?: string }) => {
      const field = item.loc?.filter((part) => part !== 'body').join('.')
      return `${field ? `${field}: ` : ''}${item.msg || 'Invalid input.'}`
    }).join(' ')
  }
  return fallback
}

export async function api<T>(path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(45_000),
      cache: 'no-store',
    })
  } catch (error) {
    const timedOut = error instanceof DOMException && (error.name === 'TimeoutError' || error.name === 'AbortError')
    throw new ApiError(timedOut
      ? 'The request timed out. Refresh the workspace to check whether it completed before trying again.'
      : 'Cannot reach the API. Check that the backend is running, then refresh the workspace.', null)
  }
  const text = await response.text()
  let data: unknown
  try { data = JSON.parse(text) } catch { data = null }
  if (!response.ok) {
    throw new ApiError(errorDetail(data, `The API returned HTTP ${response.status}. Try refreshing the workspace.`), response.status, data)
  }
  if (data === null) throw new ApiError('The API returned an unexpected response. Refresh the workspace.', response.status)
  return data as T
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred.'
}
