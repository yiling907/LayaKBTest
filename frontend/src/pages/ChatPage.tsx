import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { queryKB, QueryResponse } from '../api/client'
import './ChatPage.css'

interface Message {
  role: 'user' | 'assistant'
  text: string
  sources?: QueryResponse['sources']
}

const SUGGESTIONS = [
  'What does the Travel Insurance cover for medical emergencies abroad?',
  'What is the excess on the Car Hire Excess Insurance Single Trip policy?',
  'Am I covered for trip cancellation under the Backpacker policy?',
  'What are the key differences between policies before and after November 2025?',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set())
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async (question?: string) => {
    const q = (question ?? input).trim()
    if (!q || loading) return

    setMessages(prev => [...prev, { role: 'user', text: q }])
    setInput('')
    setLoading(true)

    try {
      const { data } = await queryKB(q)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: data.answer, sources: data.sources },
      ])
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: 'Something went wrong. Please try again.' },
      ])
    } finally {
      setLoading(false)
    }
  }

  const toggleSources = (idx: number) => {
    setExpandedSources(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  return (
    <div className="chat-page">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-logo">
              <span className="logo-icon">⛑</span>
              <h2>Laya Healthcare Knowledge Base</h2>
              <p>Ask anything about Travel Insurance or Car Hire Excess Insurance policies.</p>
            </div>
            <div className="suggestions">
              {SUGGESTIONS.map((s, i) => (
                <button key={i} className="suggestion-chip" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'user' ? (
              <p>{msg.text}</p>
            ) : (
              <div className="answer-body">
                <ReactMarkdown>{msg.text}</ReactMarkdown>

                {msg.sources && msg.sources.length > 0 && (
                  <div className="sources-section">
                    <button
                      className="sources-toggle"
                      onClick={() => toggleSources(i)}
                    >
                      {expandedSources.has(i) ? '▾' : '▸'} {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                    </button>
                    {expandedSources.has(i) && (
                      <div className="sources-list">
                        {msg.sources.map((s, j) => (
                          <div key={j} className="source-card">
                            <p className="source-doc">📄 {s.document}</p>
                            <p className="source-chunk">"{s.chunk}"</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="thinking-dots">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="input-row">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Ask about your Laya Healthcare policy..."
          disabled={loading}
        />
        <button onClick={() => send()} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
