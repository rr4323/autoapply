import type { ApplicationStatus } from '../api/types'

const LABELS: Record<ApplicationStatus, string> = {
  pending: 'Pending',
  scored: 'Scored',
  below_threshold: 'Below threshold',
  filling: 'Filling',
  ready_for_review: 'Ready for review',
  needs_input: 'Needs input',
  submitted: 'Submitted',
  failed: 'Failed',
}

// One visual tone per rough outcome bucket rather than eight distinct
// colors — the point is "good / needs you / bad / in progress" at a
// glance, not a unique swatch per enum value.
const TONE: Record<ApplicationStatus, 'neutral' | 'progress' | 'review' | 'good' | 'bad'> = {
  pending: 'neutral',
  scored: 'progress',
  below_threshold: 'neutral',
  filling: 'progress',
  ready_for_review: 'review',
  needs_input: 'review',
  submitted: 'good',
  failed: 'bad',
}

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <span className={`status-badge status-badge--${TONE[status]}`}>{LABELS[status] ?? status}</span>
}
