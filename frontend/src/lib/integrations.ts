import { getJson } from './api'

export type IntegrationState = 'live' | 'sample' | 'signed_out' | 'blocked' | 'not_configured'

export interface Integration {
  id: 'entra' | 'viva_engage' | 'pluralsight' | 'microsoft_learn'
  name: string
  state: IntegrationState
  summary: string
  /** The system's own reason for the last failure. */
  blocking: string
  needs: { what: string; setting: string; met: boolean }[]
  calls: string[]
  code: string
  docs: { label: string; url: string }[]
}

export const fetchIntegrations = (signal?: AbortSignal) => getJson<Integration[]>('/api/integrations', signal)

export const STATE_LABEL: Record<IntegrationState, string> = {
  live: 'Live',
  sample: 'Sample data',
  signed_out: 'Ready to sign in',
  blocked: 'Blocked',
  not_configured: 'Not set up',
}

/** Starts the Microsoft sign-in round trip. A navigation, not a fetch: Microsoft's page takes over. */
export function signInWithMicrosoft(next = '/community') {
  window.location.assign(`/api/auth/microsoft/login?next=${encodeURIComponent(next)}`)
}
