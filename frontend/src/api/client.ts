import type {
  ApplicationCreated,
  ApplicationDetail,
  ApplicationSummary,
  ApiErrorBody,
  ConfirmSubmitResult,
  Profile,
  PutProfileRequest,
  PutProfileResult,
} from './types'

// Relative paths only — Vite's dev-server proxy (vite.config.ts) forwards
// /api/* to the Go control plane; a real deployment sits both apps
// behind one origin the same way, so no base URL ever needs configuring.
const API_ROOT = '/api/v1'

export class ApiError extends Error {
  code: string
  status: number

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message)
    this.code = body.error.code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(
      res.status,
      body ?? { error: { code: 'unknown', message: `request failed with status ${res.status}` } },
    )
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

export interface ListApplicationsParams {
  status?: string[]
  limit?: number
}

export function listApplications(
  params: ListApplicationsParams = {},
): Promise<{ data: ApplicationSummary[]; next_cursor: string | null }> {
  const search = new URLSearchParams()
  for (const status of params.status ?? []) search.append('status', status)
  if (params.limit) search.set('limit', String(params.limit))
  const qs = search.toString()
  return request(`/applications${qs ? `?${qs}` : ''}`)
}

export function getApplication(id: string): Promise<ApplicationDetail> {
  return request(`/applications/${id}`)
}

export function createApplication(input: {
  jdUrl?: string
  jdText?: string
}): Promise<ApplicationCreated> {
  return request('/applications', {
    method: 'POST',
    body: JSON.stringify({ jd_url: input.jdUrl || undefined, jd_text: input.jdText || undefined }),
  })
}

export function confirmSubmit(id: string): Promise<ConfirmSubmitResult> {
  return request(`/applications/${id}/confirm-submit`, { method: 'POST' })
}

export function getProfile(): Promise<Profile> {
  return request('/profile')
}

export function putProfile(input: PutProfileRequest): Promise<PutProfileResult> {
  return request('/profile', { method: 'PUT', body: JSON.stringify(input) })
}
