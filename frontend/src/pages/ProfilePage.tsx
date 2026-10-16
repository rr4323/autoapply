import { useEffect, useState } from 'react'
import { ApiError, getProfile, putProfile } from '../api/client'
import type { ExperienceEntry } from '../api/types'

function emptyEntry(): ExperienceEntry {
  return {
    id: crypto.randomUUID(),
    company: '',
    title: '',
    start_date: '',
    end_date: null,
    bullets: [''],
  }
}

export function ProfilePage() {
  const [skillsText, setSkillsText] = useState('')
  const [experience, setExperience] = useState<ExperienceEntry[]>([emptyEntry()])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    getProfile()
      .then((profile) => {
        setSkillsText(profile.skills.join(', '))
        setExperience(profile.experience.length > 0 ? profile.experience : [emptyEntry()])
      })
      .catch((err) => {
        // No profile saved yet is expected for a brand-new user, not an
        // error — everything else genuinely is.
        if (!(err instanceof ApiError && err.status === 404)) {
          setError(err instanceof Error ? err.message : String(err))
        }
      })
      .finally(() => setLoading(false))
  }, [])

  function updateEntry(index: number, patch: Partial<ExperienceEntry>) {
    setExperience((prev) => prev.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }

  function updateBullets(index: number, raw: string) {
    updateEntry(index, { bullets: raw.split('\n') })
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const skills = skillsText
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const cleanedExperience = experience.map((entry) => ({
        ...entry,
        bullets: entry.bullets.map((b) => b.trim()).filter(Boolean),
      }))
      await putProfile({ base_resume_doc_id: null, skills, experience: cleanedExperience })
      setSavedAt(Date.now())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p>Loading…</p>

  return (
    <div className="page-narrow">
      <h1>Profile</h1>
      <p className="muted">
        This is what the Scoring and Generator agents cite from — every claim in a generated
        resume or cover letter has to trace back to a bullet here.
      </p>
      <p className="callout callout--muted">
        Known gap: saving here doesn't yet re-index your profile for retrieval
        (docs/BACKEND_BUILD_STEPS.md Step 25's trigger isn't wired up). Scoring on new
        applications won't reflect edits made on this page until that's built.
      </p>

      <label className="field">
        <span>Skills (comma-separated)</span>
        <input
          type="text"
          value={skillsText}
          onChange={(e) => setSkillsText(e.target.value)}
          placeholder="Go, PostgreSQL, distributed systems"
        />
      </label>

      <h2>Experience</h2>
      {experience.map((entry, i) => (
        <div className="experience-entry" key={entry.id}>
          <div className="experience-entry__row">
            <input
              type="text"
              placeholder="Company"
              value={entry.company}
              onChange={(e) => updateEntry(i, { company: e.target.value })}
            />
            <input
              type="text"
              placeholder="Title"
              value={entry.title}
              onChange={(e) => updateEntry(i, { title: e.target.value })}
            />
          </div>
          <div className="experience-entry__row">
            <input
              type="text"
              placeholder="Start date (YYYY-MM)"
              value={entry.start_date}
              onChange={(e) => updateEntry(i, { start_date: e.target.value })}
            />
            <input
              type="text"
              placeholder="End date (blank = present)"
              value={entry.end_date ?? ''}
              onChange={(e) => updateEntry(i, { end_date: e.target.value || null })}
            />
          </div>
          <textarea
            placeholder="One bullet per line"
            value={entry.bullets.join('\n')}
            onChange={(e) => updateBullets(i, e.target.value)}
            rows={4}
          />
          <button
            type="button"
            className="button button--ghost"
            onClick={() => setExperience((prev) => prev.filter((_, idx) => idx !== i))}
          >
            Remove entry
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button button--ghost"
        onClick={() => setExperience((prev) => [...prev, emptyEntry()])}
      >
        + Add experience entry
      </button>

      {error && <p className="error">{error}</p>}
      {savedAt && !saving && <p className="success">Saved.</p>}

      <div>
        <button type="button" className="button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </div>
    </div>
  )
}
