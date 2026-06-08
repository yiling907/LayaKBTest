import { useState, useRef, useEffect } from 'react'
import { queryKB, QueryResponse } from '../api/client'
import SourceCard from '../components/SourceCard'
import './ChatPage.css'

interface Message {
  role: 'user' | 'assistant'
  text: string
  sources?: QueryResponse['sources']
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const question = input.trim()
    if (!question || loading) return

    setMessages(prev => [...prev, { role: 'user', text: question }])
    setInput('')
    setLoading(true)

    try {
      const { data } = await queryKB(question)
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

  return (
    <div className="chat-page">
      <div className="messages">
        {messages.length === 0 && (
          <p className="empty-state">Ask a question to get started.</p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <p>{msg.text}</p>
            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                <p className="sources-label">Sources</p>
                {msg.sources.map((s, j) => (
                  <SourceCard key={j} document={s.document} chunk={s.chunk} />
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <p className="thinking">Thinking...</p>
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
          placeholder="Ask a question..."
          disabled={loading}
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
