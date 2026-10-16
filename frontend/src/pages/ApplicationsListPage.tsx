import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listApplications } from '../api/client'
import type { ApplicationSummary } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'

export function ApplicationsListPage() {
  const [applications, setApplications] = useState<ApplicationSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listApplications({ limit: 50 })
      .then((res) => {
        if (!cancelled) setApplications(res.data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <p className="error">Failed to load applications: {error}</p>
  if (!applications) return <p>Loading…</p>

  if (applications.length === 0) {
    return (
      <div className="empty-state">
        <p>No applications yet.</p>
        <Link to="/apply" className="button">
          Submit a job description
        </Link>
      </div>
    )
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Role</th>
          <th>Company</th>
          <th>Status</th>
          <th>Score</th>
          <th>Submitted</th>
        </tr>
      </thead>
      <tbody>
        {applications.map((app) => (
          <tr key={app.id}>
            <td>
              <Link to={`/applications/${app.id}`}>{app.role_title ?? '(untitled role)'}</Link>
            </td>
            <td>{app.company ?? '—'}</td>
            <td>
              <StatusBadge status={app.status} />
            </td>
            <td>{app.jd_fit_score ?? '—'}</td>
            <td>{app.submitted_at ? new Date(app.submitted_at).toLocaleString() : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
