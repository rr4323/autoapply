import type { ScoreBreakdown } from '../api/types'

const SIGNAL_LABELS: Record<string, string> = {
  keyword_overlap: 'Skills/keyword overlap',
  retrieval_relevance: 'Profile relevance (retrieval)',
  llm_semantic: 'Semantic fit (LLM)',
}

// This panel is the product's actual point (see docs/PRD.md — the trust
// layer, not the autofill): show the honest signal breakdown a score
// came from, not just a final number, so "why" is never a black box.
export function ScoreBreakdownView({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div className="score-breakdown">
      <div className="score-breakdown__total">
        <span className="score-breakdown__number">{breakdown.score}</span>
        <span className="score-breakdown__label">/ 100</span>
      </div>
      <ul className="score-breakdown__signals">
        {Object.entries(breakdown.signals).map(([name, signal]) => (
          <li key={name}>
            <div className="score-breakdown__signal-header">
              <span>{SIGNAL_LABELS[name] ?? name}</span>
              <span>{Math.round(signal.value * 100)}%</span>
            </div>
            <div className="score-breakdown__bar">
              <div
                className="score-breakdown__bar-fill"
                style={{ width: `${Math.min(100, Math.max(0, signal.value * 100))}%` }}
              />
            </div>
            <div className="score-breakdown__weight">
              weight {Math.round(signal.weight * 100)}% · contributes {(signal.contribution * 100).toFixed(1)} pts
            </div>
          </li>
        ))}
      </ul>
      <p className="score-breakdown__version">model: {breakdown.scoring_model_version}</p>
    </div>
  )
}
