
import { useEffect, useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { marked } from 'marked'
import './App.css'

type ApiSession = {
  id: string
  title: string
  user_id: string | null
  created_at: string
  updated_at: string
}

type ApiMessage = {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: Date
}

type ChatSession = {
  id: string
  title: string
  messages: Message[]
}

type Artifact = {
  title: string
  content: string
  type: 'html' | 'markdown'
}

type GenerateResponse = {
  response: string
  provider: string
  model: string
}

const API_BASE = '/api/v1'

function looksLikeHtml(content: string) {
  return /<!doctype html|<html[\s>]|<body[\s>]|<div[\s>]|<article[\s>]/i.test(
      content.trim(),
  )
}

async function apiRequest<T>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    let detail = `Request failed (${response.status})`

    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        detail = body.detail
      }
    } catch {
      // Keep the fallback error message.
    }

    throw new Error(detail)
  }

  return response.json() as Promise<T>
}

function toMessage(message: ApiMessage): Message {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: new Date(message.created_at),
  }
}

function getSessionTitle(question: string) {
  return (
      question.slice(0, 38) + (question.length > 38 ? 'â€¦' : '')
  )
}

function App() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(
      null,
  )
  const [input, setInput] = useState('')
  const [writingMode, setWritingMode] = useState<'general' | 'essay'>(
      'general',
  )
  const [isLoading, setIsLoading] = useState(false)
  const [isInitializing, setIsInitializing] = useState(true)
  const [error, setError] = useState('')
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [showArtifact, setShowArtifact] = useState(true)

  const activeSession = sessions.find(
      (session) => session.id === activeSessionId,
  )
  const messages = activeSession?.messages ?? []

  // Load persistent sessions when the app starts.
  useEffect(() => {
    let cancelled = false

    async function loadSessions() {
      try {
        const savedSessions =
            await apiRequest<ApiSession[]>('/sessions')

        if (cancelled) return

        setSessions(
            savedSessions.map((session) => ({
              id: session.id,
              title: session.title,
              messages: [],
            })),
        )
      } catch (requestError) {
        if (!cancelled) {
          setError(
              requestError instanceof TypeError
                  ? 'Could not connect to the backend. Check that FastAPI is running.'
                  : requestError instanceof Error
                      ? requestError.message
                      : 'Could not load saved conversations.',
          )
        }
      } finally {
        if (!cancelled) {
          setIsInitializing(false)
        }
      }
    }

    void loadSessions()

    return () => {
      cancelled = true
    }
  }, [])

  async function loadSessionMessages(sessionId: string) {
    const savedMessages = await apiRequest<ApiMessage[]>(
        `/sessions/${sessionId}/messages`,
    )

    const convertedMessages = savedMessages.map(toMessage)

    setSessions((previous) =>
        previous.map((session) =>
            session.id === sessionId
                ? { ...session, messages: convertedMessages }
                : session,
        ),
    )
  }

  async function createNewChat() {
    if (isLoading) return

    setError('')
    setArtifact(null)
    setInput('')

    try {
      const created = await apiRequest<ApiSession>('/sessions', {
        method: 'POST',
        body: JSON.stringify({ title: 'New conversation' }),
      })

      const newSession: ChatSession = {
        id: created.id,
        title: created.title,
        messages: [],
      }

      setSessions((previous) => [
        newSession,
        ...previous.filter((session) => session.id !== created.id),
      ])
      setActiveSessionId(created.id)
    } catch (requestError) {
      setError(
          requestError instanceof TypeError
              ? 'Could not connect to the backend. Check that FastAPI is running.'
              : requestError instanceof Error
                  ? requestError.message
                  : 'Could not create a conversation.',
      )
    }
  }

  async function selectSession(sessionId: string) {
    if (isLoading || sessionId === activeSessionId) return

    setActiveSessionId(sessionId)
    setError('')
    setArtifact(null)

    try {
      await loadSessionMessages(sessionId)
    } catch (requestError) {
      setError(
          requestError instanceof Error
              ? requestError.message
              : 'Could not load conversation messages.',
      )
    }
  }

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault()

    const question = input.trim()
    if (!question || isLoading) return

    setError('')
    setInput('')
    setArtifact(null)
    setIsLoading(true)

    let sessionId = activeSessionId
    let sessionCreated = false

    try {
      // Create a real database session if this is the first message.
      if (!sessionId) {
        const created = await apiRequest<ApiSession>('/sessions', {
          method: 'POST',
          body: JSON.stringify({
            title: getSessionTitle(question),
          }),
        })

        sessionId = created.id
        sessionCreated = true

        setSessions((previous) => [
          {
            id: created.id,
            title: created.title,
            messages: [],
          },
          ...previous,
        ])
        setActiveSessionId(created.id)
      }

      if (!sessionId) {
        throw new Error('Could not establish a conversation session.')
      }

      // Persist the user's message before generating the response.
      const savedUserMessage = await apiRequest<ApiMessage>(
          `/sessions/${sessionId}/messages`,
          {
            method: 'POST',
            body: JSON.stringify({
              role: 'user',
              content: question,
            }),
          },
      )

      const userMessage = toMessage(savedUserMessage)

      setSessions((previous) =>
          previous.map((session) => {
            if (session.id !== sessionId) return session

            const hasPreviousUserMessage = session.messages.some(
                (message) => message.role === 'user',
            )

            return {
              ...session,
              title:
                  !hasPreviousUserMessage &&
                  (session.title === 'New conversation' || sessionCreated)
                      ? getSessionTitle(question)
                      : session.title,
              messages: [...session.messages, userMessage],
            }
          }),
      )

      // Generate an answer using the existing transcript-grounded API.
      const generated = await apiRequest<GenerateResponse>(
          '/ai/generate',
          {
            method: 'POST',
            body: JSON.stringify({
              prompt: question,
              writing_mode: writingMode,
            }),
          },
      )

      // Persist the assistant's answer as well.
      const savedAssistantMessage = await apiRequest<ApiMessage>(
          `/sessions/${sessionId}/messages`,
          {
            method: 'POST',
            body: JSON.stringify({
              role: 'assistant',
              content: generated.response,
            }),
          },
      )

      const assistantMessage = toMessage(savedAssistantMessage)

      setSessions((previous) =>
          previous.map((session) =>
              session.id === sessionId
                  ? {
                    ...session,
                    messages: [...session.messages, assistantMessage],
                  }
                  : session,
          ),
      )

      if (looksLikeHtml(generated.response)) {
        setArtifact({
          title: 'Generated HTML',
          content: generated.response,
          type: 'html',
        })
        setShowArtifact(true)
      } else if (
          writingMode === 'essay' &&
          generated.response.trim().length > 500
      ) {
        setArtifact({
          title: 'Generated essay',
          content: generated.response,
          type: 'markdown',
        })
        setShowArtifact(true)
      }
    } catch (requestError) {
      setError(
          requestError instanceof TypeError
              ? 'Could not connect to the backend. Check that FastAPI is running and the frontend API proxy is configured.'
              : requestError instanceof Error
                  ? requestError.message
                  : 'Something went wrong.',
      )

      // Reload from the database so a saved user message is not lost
      // from the UI if generation or response persistence fails.
      if (sessionId) {
        try {
          await loadSessionMessages(sessionId)
        } catch {
          // Keep the original error visible.
        }
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function handleDownloadArtifact(format: 'markdown' | 'html') {
    if (!artifact) return

    const escapeHtml = (value: string) =>
      value.replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')

    const markdownContent = artifact.content
    const renderedBody = artifact.type === 'html'
      ? artifact.content
      : await marked.parse(artifact.content, { gfm: true, breaks: false })

    const htmlContent = artifact.type === 'html'
      ? artifact.content
      : `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(artifact.title)}</title>
<style>
body{font-family:system-ui,sans-serif;max-width:850px;margin:40px auto;padding:0 24px;line-height:1.65;color:#202124}
h1,h2,h3{line-height:1.25;margin-top:1.5em}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f4f5;padding:16px;border-radius:8px}
blockquote{border-left:3px solid #bbb;margin-left:0;padding-left:16px;color:#555}
img{max-width:100%}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ddd;padding:8px;text-align:left}
</style>
</head>
<body><article>${renderedBody}</article></body>
</html>`

    const content = format === 'html' ? htmlContent : markdownContent
    const mimeType = format === 'html' ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8'
    const filename = format === 'html' ? 'artifact.html' : 'artifact.md'
    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
      <div
          className={`app-shell ${showArtifact && artifact ? 'with-artifact' : ''}`}
      >
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">L</div>
            <div>
              <div className="brand-name">Lenny Growth</div>
              <div className="brand-caption">YOUR PRODUCT PARTNER</div>
            </div>
          </div>

          <button
              className="new-chat-button"
              onClick={() => void createNewChat()}
              disabled={isLoading}
          >
            <span>ï¼‹</span> New conversation
          </button>

          <div className="sidebar-label">YOUR CHATS</div>

          <div className="session-list">
            {isInitializing ? (
                <p className="empty-history">Loading conversationsâ€¦</p>
            ) : sessions.length === 0 ? (
                <p className="empty-history">
                  Your conversations will appear here.
                </p>
            ) : (
                sessions.map((session) => (
                    <button
                        className={`session-item ${
                            session.id === activeSessionId ? 'active' : ''
                        }`}
                        key={session.id}
                        onClick={() => void selectSession(session.id)}
                        disabled={isLoading}
                    >
                      <span className="session-icon">â—·</span>
                      <span className="session-title">{session.title}</span>
                    </button>
                ))
            )}
          </div>

          <div className="sidebar-footer">
            <div className="knowledge-icon">âœ³</div>
            <div>
              <strong>Transcript-grounded AI</strong>
              <p>Answers are based on retrieved Lenny's transcripts.</p>
            </div>
          </div>
        </aside>

        <main className="main-panel">
          <header className="topbar">
            <div className="mobile-brand">
              <div className="brand-mark small">L</div>
              <strong>Lenny Growth Assistant</strong>
            </div>

            <div className="topbar-status">
              <span className="status-dot" />
              <span>Transcript knowledge base</span>
            </div>

            <div className="mode-control">
              <label htmlFor="writing-mode">Mode</label>
              <select
                  id="writing-mode"
                  value={writingMode}
                  onChange={(event) =>
                      setWritingMode(event.target.value as 'general' | 'essay')
                  }
                  disabled={isLoading}
              >
                <option value="general">Ask Lenny</option>
                <option value="essay">Essay writer</option>
              </select>
            </div>
          </header>

          <section className="conversation">
            {messages.length === 0 ? (
                <div className="welcome">
                  <div className="welcome-icon">âœ³</div>
                  <div className="eyebrow">YOUR AI GROWTH PARTNER</div>
                  <h1>
                    Good ideas grow
                    <br />
                    from good questions.
                  </h1>
                  <p className="welcome-copy">
                    Explore product, growth, leadership, and startup lessons
                    grounded in Lenny's Podcast and Newsletter transcripts.
                  </p>

                  <div className="suggestion-grid">
                    <button
                        className="suggestion-card"
                        onClick={() =>
                            setInput('How can a startup improve user activation?')
                        }
                    >
                      <span className="suggestion-symbol">â†—</span>
                      <strong>Improve activation</strong>
                      <span>Help new users experience value sooner.</span>
                    </button>

                    <button
                        className="suggestion-card"
                        onClick={() =>
                            setInput(
                                'What should a product team consider when prioritizing its roadmap?',
                            )
                        }
                    >
                      <span className="suggestion-symbol">â—‡</span>
                      <strong>Prioritize a roadmap</strong>
                      <span>Think through product trade-offs.</span>
                    </button>

                    <button
                        className="suggestion-card"
                        onClick={() =>
                            setInput(
                                'What can founders learn about product-market fit?',
                            )
                        }
                    >
                      <span className="suggestion-symbol">â—Ž</span>
                      <strong>Find product-market fit</strong>
                      <span>Explore lessons from relevant episodes.</span>
                    </button>

                    <button
                        className="suggestion-card"
                        onClick={() => {
                          setWritingMode('essay')
                          setInput(
                              'Write an essay about building a product-led growth strategy.',
                          )
                        }}
                    >
                      <span className="suggestion-symbol">â–¤</span>
                      <strong>Write an essay</strong>
                      <span>Turn transcript insights into a structured piece.</span>
                    </button>
                  </div>
                </div>
            ) : (
                <div className="message-list">
                  {messages.map((message) => (
                      <article
                          className={`message-row ${message.role}`}
                          key={message.id}
                      >
                        <div className={`avatar ${message.role}`}>
                          {message.role === 'user' ? 'Y' : 'L'}
                        </div>

                        <div className="message-content">
                          <div className="message-meta">
                            <strong>
                              {message.role === 'user'
                                  ? 'You'
                                  : 'Lenny Growth Assistant'}
                            </strong>
                            <span>
                        {Number.isNaN(message.createdAt.getTime())
                            ? ''
                            : message.createdAt.toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                      </span>
                          </div>

                          {message.role === 'assistant' ? (
                              <div className="markdown-body">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {message.content}
                                </ReactMarkdown>
                              </div>
                          ) : (
                              <p className="user-message-text">{message.content}</p>
                          )}
                        </div>
                      </article>
                  ))}

                  {isLoading && (
                      <div className="message-row assistant">
                        <div className="avatar assistant">L</div>
                        <div className="loading-content">
                          <strong>Thinking from the transcripts</strong>
                          <div className="typing-indicator">
                            <span />
                            <span />
                            <span />
                          </div>
                        </div>
                      </div>
                  )}

                  <div className="conversation-end" />
                </div>
            )}
          </section>

          <div className="composer-area">
            {error && (
                <div className="error-banner">
                  <span>!</span>
                  <p>{error}</p>
                  <button
                      onClick={() => setError('')}
                      aria-label="Dismiss error"
                  >
                    Ã—
                  </button>
                </div>
            )}

            <form className="composer" onSubmit={sendMessage}>
            <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    void sendMessage()
                  }
                }}
                placeholder={
                  writingMode === 'essay'
                      ? 'Describe the essay you want to createâ€¦'
                      : 'Ask a question about product, growth, or leadershipâ€¦'
                }
                rows={2}
                disabled={isLoading}
            />

              <div className="composer-bottom">
              <span>
                <kbd>Enter</kbd> to send Â· <kbd>Shift + Enter</kbd> for a new
                line
              </span>
                <button
                    className="send-button"
                    type="submit"
                    disabled={isLoading || !input.trim()}
                    aria-label="Send message"
                >
                  {isLoading ? '...' : (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M12 19V5M5 12l7-7 7 7"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)}
                </button>
              </div>
            </form>

            <p className="disclaimer">
              Responses are grounded in retrieved transcript excerpts. Verify
              important decisions against the cited sources.
            </p>
          </div>
        </main>

        {showArtifact && artifact && (
            <aside className="artifact-panel">
              <header className="artifact-header">
                <div>
                  <span className="artifact-kicker">WORKSPACE</span>
                  <h2>{artifact.title}</h2>
                </div>

                <div className="artifact-actions">
                  <button onClick={() => handleDownloadArtifact('markdown')} title="Download Markdown">
                    Download .md
                  </button>
                  <button onClick={() => handleDownloadArtifact('html')} title="Download HTML">
                    Download .html
                  </button>
                  <button
                      onClick={() => setShowArtifact(false)}
                      title="Close artifact viewer"
                  >
                    Close
                  </button>
                </div>
              </header>

              <div className="artifact-tabs">
                <span className="active">Preview</span>
                <span>{artifact.type === 'html' ? 'HTML' : 'Markdown'}</span>
              </div>

              {artifact.type === 'html' ? (
                  <iframe
                      className="artifact-iframe"
                      title="Generated HTML artifact"
                      sandbox=""
                      srcDoc={artifact.content}
                  />
              ) : (
                  <div className="artifact-markdown markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {artifact.content}
                    </ReactMarkdown>
                  </div>
              )}
            </aside>
        )}
      </div>
  )
}

export default App


