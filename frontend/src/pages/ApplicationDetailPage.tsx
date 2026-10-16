import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { confirmSubmit, getApplication } from '../api/client'
import type { ApplicationDetail } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { ScoreBreakdownView } from '../components/ScoreBreakdownView'

const IN_PROGRESS_STATUSES = new Set(['pending', 'scored', 'filling'])
const POLL_INTERVAL_MS = 3000

const DOCUMENT_LABELS: Record<string, string> = {
  resume: 'Resume',
  cover_letter: 'Cover letter',
  screener_answer: 'Screener answers',
}

export function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [application, setApplication] = useState<ApplicationDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const detail = await getApplication(id!)
        if (cancelled) return
        setApplication(detail)
        if (IN_PROGRESS_STATUSES.has(detail.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [id])

  async function handleConfirmSubmit() {
    if (!id) return
    setConfirming(true)
    try {
      const result = await confirmSubmit(id)
      setApplication((prev) =>
        prev ? { ...prev, status: result.status as ApplicationDetail['status'], submitted_at: result.submitted_at } : prev,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setConfirming(false)
    }
  }

  if (error) return <p className="error">Failed to load application: {error}</p>
  if (!application) return <p>Loading…</p>

  return (
    <div className="detail">
      <div className="detail__header">
        <div>
          <h1>{application.role_title ?? '(untitled role)'}</h1>
          <p className="muted">{application.company ?? 'Unknown company'}</p>
        </div>
        <StatusBadge status={application.status} />
      </div>

      {application.jd_url && (
        <p>
          <a href={application.jd_url} target="_blank" rel="noreferrer">
            {application.jd_url}
          </a>
        </p>
      )}

      {IN_PROGRESS_STATUSES.has(application.status) && (
        <p className="muted">Agents are still working on this application — this page updates automatically.</p>
      )}

      {application.status === 'ready_for_review' && (
        <div className="callout">
          <p>This application is ready to submit. Review the details below, then confirm.</p>
          <button className="button" onClick={handleConfirmSubmit} disabled={confirming}>
            {confirming ? 'Submitting…' : 'Confirm submit'}
          </button>
        </div>
      )}

      {application.status === 'below_threshold' && (
        <div className="callout callout--muted">
          <p>This role scored below the auto-generate threshold — no documents were generated.</p>
        </div>
      )}

      {application.score_breakdown && (
        <section>
          <h2>Score breakdown</h2>
          <ScoreBreakdownView breakdown={application.score_breakdown} />
        </section>
      )}

      {application.generated_documents.length > 0 && (
        <section>
          <h2>Generated documents</h2>
          <ul className="document-list">
            {application.generated_documents.map((doc) => (
              <li key={doc.id}>
                <span>{DOCUMENT_LABELS[doc.type] ?? doc.type}</span>
                <span className="muted">
                  groundedness {Math.round(doc.groundedness_score * 100)}% · {doc.source_chunk_ids.length} cited
                  source{doc.source_chunk_ids.length === 1 ? '' : 's'}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {application.policy_decisions.length > 0 && (
        <section>
          <h2>Policy decisions</h2>
          <ul className="decision-list">
            {application.policy_decisions.map((decision, i) => (
              <li key={i}>
                <div className="decision-list__head">
                  <strong>{decision.decision_point.replace('_', ' ')}</strong>
                  <span>{decision.action}</span>
                </div>
                <ul>
                  {decision.reasons.map((reason, j) => (
                    <li key={j} className="muted">
                      {reason}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
