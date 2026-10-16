import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createApplication } from '../api/client'

type Mode = 'url' | 'text'

export function NewApplicationPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('url')
  const [jdUrl, setJdUrl] = useState('')
  const [jdText, setJdText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const created = await createApplication(
        mode === 'url' ? { jdUrl } : { jdText },
      )
      navigate(`/applications/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="page-narrow">
      <h1>Submit a job description</h1>
      <p className="muted">
        The Scraper, Retriever, Scoring, and Policy Engine agents pick this up automatically —
        watch the application's status change on its detail page.
      </p>
      <form onSubmit={handleSubmit} className="form">
        <div className="mode-toggle">
          <label>
            <input type="radio" checked={mode === 'url'} onChange={() => setMode('url')} />
            JD URL
          </label>
          <label>
            <input type="radio" checked={mode === 'text'} onChange={() => setMode('text')} />
            Paste JD text
          </label>
        </div>
        {mode === 'url' ? (
          <input
            type="url"
            placeholder="https://boards.greenhouse.io/..."
            value={jdUrl}
            onChange={(e) => setJdUrl(e.target.value)}
            required
          />
        ) : (
          <textarea
            placeholder="Paste the full job description..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={10}
            required
          />
        )}
        {error && <p className="error">{error}</p>}
        <button type="submit" className="button" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </form>
    </div>
  )
}
