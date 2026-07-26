import { useState } from 'react'
import api from '../api/client'
import './EvalPage.css'

const CATEGORIES = ['all', 'kb_retrieval', 'policy_version', 'personalised', 'edge_case']

interface ScoreDetail {
  relevance: number
  faithfulness: number
  completeness: number
  personalisation: number | null
  reasoning: string
}

interface EvalResult {
  id: string
  category: string
  question: string
  user_id: string | null
  answer: string
  sources_count: number
  hard_pass: boolean
  hard_failures: string[]
  scores: ScoreDetail
  overall: number
  error: string | null
}

interface EvalSummary {
  total: number
  hard_passed: number
  overall_avg: number
  by_category: Record<string, { avg: number; count: number }>
}

export default function EvalPage() {
  const [category, setCategory] = useState('all')
  const [running, setRunning] = useState(false)
  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [results, setResults] = useState<EvalResult[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')

  const runEval = async () => {
    setRunning(true)
    setError('')
    setSummary(null)
    setResults([])
    try {
      const { data } = await api.post('/evaluate', {
        category: category === 'all' ? null : category,
      })
      setSummary(data.summary)
      setResults(data.results)
    } catch (e: unknown) {
      setError('Evaluation failed. Check backend logs.')
    } finally {
      setRunning(false)
    }
  }

  const toggle = (id: string) =>
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const scoreColor = (v: number) =>
    v >= 0.8 ? '#065f46' : v >= 0.6 ? '#92400e' : '#991b1b'

  const scoreBg = (v: number) =>
    v >= 0.8 ? '#d1fae5' : v >= 0.6 ? '#fef3c7' : '#fee2e2'

  return (
    <div className="eval-page">
      <h1>Agent Evaluation</h1>
      <p className="eval-desc">
        LLM-as-judge evaluation across {CATEGORIES.length - 1} categories.
        Scores each response on relevance, faithfulness, completeness, and personalisation.
      </p>

      <div className="eval-controls">
        <div className="category-tabs">
          {CATEGORIES.map(c => (
            <button
              key={c}
              className={`tab ${category === c ? 'active' : ''}`}
              onClick={() => setCategory(c)}
              disabled={running}
            >
              {c === 'all' ? 'All' : c.replace('_', ' ')}
            </button>
          ))}
        </div>
        <button className="btn-run" onClick={runEval} disabled={running}>
          {running ? 'Running…' : '▶ Run Evaluation'}
        </button>
      </div>

      {running && (
        <div className="eval-progress">
          <div className="progress-bar" />
          <p>Running test cases — this may take a few minutes…</p>
        </div>
      )}

      {error && <p className="eval-error">{error}</p>}

      {summary && (
        <div className="summary-grid">
          <div className="summary-card">
            <div className="summary-value">{summary.overall_avg.toFixed(3)}</div>
            <div className="summary-label">Overall Score</div>
          </div>
          <div className="summary-card">
            <div className="summary-value">{summary.hard_passed}/{summary.total}</div>
            <div className="summary-label">Hard Checks</div>
          </div>
          {Object.entries(summary.by_category).map(([cat, s]) => (
            <div className="summary-card" key={cat}>
              <div className="summary-value">{s.avg.toFixed(3)}</div>
              <div className="summary-label">{cat.replace('_', ' ')} (n={s.count})</div>
            </div>
          ))}
        </div>
      )}

      {results.length > 0 && (
        <div className="results-list">
          {results.map(r => (
            <div key={r.id} className={`result-card ${r.hard_pass ? '' : 'fail'}`}>
              <div className="result-header" onClick={() => toggle(r.id)}>
                <div className="result-meta">
                  <span className="result-id">{r.id}</span>
                  <span className="result-cat">{r.category}</span>
                  {r.user_id && <span className="result-user">👤 {r.user_id}</span>}
                  {!r.hard_pass && <span className="result-hardfail">⚠ hard check failed</span>}
                </div>
                <div className="result-scores">
                  {(['relevance', 'faithfulness', 'completeness'] as const).map(k => (
                    <span
                      key={k}
                      className="score-chip"
                      style={{ background: scoreBg(r.scores[k]), color: scoreColor(r.scores[k]) }}
                    >
                      {k[0].toUpperCase()}={r.scores[k].toFixed(2)}
                    </span>
                  ))}
                  {r.scores.personalisation != null && (
                    <span
                      className="score-chip"
                      style={{ background: scoreBg(r.scores.personalisation), color: scoreColor(r.scores.personalisation) }}
                    >
                      P={r.scores.personalisation.toFixed(2)}
                    </span>
                  )}
                  <span className="overall-chip">⌀ {r.overall.toFixed(3)}</span>
                  <span className="expand-toggle">{expanded.has(r.id) ? '▾' : '▸'}</span>
                </div>
              </div>
              <div className="result-question">{r.question}</div>

              {expanded.has(r.id) && (
                <div className="result-detail">
                  <div className="detail-reasoning">
                    <strong>Judge reasoning:</strong> {r.scores.reasoning}
                  </div>
                  {r.hard_failures.length > 0 && (
                    <div className="detail-failures">
                      {r.hard_failures.map((f, i) => <div key={i}>⚠ {f}</div>)}
                    </div>
                  )}
                  <div className="detail-answer">
                    <strong>Answer ({r.sources_count} source{r.sources_count !== 1 ? 's' : ''}):</strong>
                    <pre>{r.answer}</pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
