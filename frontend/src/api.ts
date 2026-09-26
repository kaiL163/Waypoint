import type { Dataset, Plan, ServiceRequest, Transport } from './model'

const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') || ''

function errorDetail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg: unknown }).msg)
        return JSON.stringify(item)
      })
      .filter(Boolean)
      .join('; ') || fallback
  }
  return fallback
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    let detail = `Сервер вернул ${response.status}.`
    try {
      detail = errorDetail(await response.json(), detail)
    } catch {
      /* ignore */
    }
    throw Error(detail)
  }
  return response.json() as Promise<T>
}

export type DemoScenarioInfo = { id: string; title: string; description: string }

export type UrgentInput = {
  address: string
  lat: number
  lng: number
  eventTime: string
  windowStart: string
  windowEnd: string
  durationMinutes: number
  requiredSkill: string
  requiredTransport?: Transport
}

export type ReplanEvent =
  | { eventTime: string; type: 'urgent_request'; input: UrgentInput }
  | { eventTime: string; type: 'urgent_request'; request: ServiceRequest }
  | { eventTime: string; type: 'cancel_request'; requestId: string }
  | { eventTime: string; type: 'engineer_unavailable'; engineerId: string }

export type ReplanResult = { dataset: Dataset; plan: Plan; baseline: Plan; changes: string[] }

export const api = {
  state: () => call<{dataset: Dataset | null; plan: Plan | null; baseline: Plan | null}>('/api/state'),
  compare: (data: Dataset) => call<ReplanResult>('/api/planning/compare', {method:'POST',body:JSON.stringify(data)}),
  demos: () => call<DemoScenarioInfo[]>('/api/data/demos'),
  demo: (scenario?: string) =>
    call<Dataset>(`/api/data/demo${scenario ? `?scenario=${encodeURIComponent(scenario)}` : ''}`, {
      method: 'POST',
    }),
  optimize: (data: Dataset, strategy: 'optimized' | 'baseline' = 'optimized') =>
    call<Plan>(`/api/planning/optimize?strategy=${strategy}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  replan: (dataset: Dataset, event: ReplanEvent, previousPlan?: Plan | null) =>
    call<ReplanResult>('/api/planning/replan', {
      method: 'POST',
      body: JSON.stringify({ dataset, event, previousPlan: previousPlan ?? null }),
    }),
  upload: async (files: FileList): Promise<Dataset> => {
    const form = new FormData()
    Array.from(files).forEach((file) => form.append('files', file))
    const response = await fetch(`${base}/api/data/upload`, { method: 'POST', body: form })
    if (!response.ok) {
      let detail = `Сервер вернул ${response.status}.`
      try {
        detail = errorDetail(await response.json(), detail)
      } catch {
        /* ignore */
      }
      throw Error(detail)
    }
    return response.json() as Promise<Dataset>
  },
}
