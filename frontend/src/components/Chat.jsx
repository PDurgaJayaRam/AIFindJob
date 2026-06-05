import React, { useState, useRef, useEffect } from 'react'

const API = ''

const PORTALS = [
  { value: 'naukri', label: 'Naukri' },
  { value: 'indeed', label: 'Indeed' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'foundit', label: 'Foundit' },
  { value: 'glassdoor', label: 'Glassdoor', disabled: true, reason: 'Disabled — Cloudflare IP blocking' },
  { value: 'timesjobs', label: 'TimesJobs' },
  { value: 'shine', label: 'Shine' },
  { value: 'cutshort', label: 'CutShort' },
  { value: 'linkedin_us', label: 'LinkedIn US' },
  { value: 'glassdoor_us', label: 'Glassdoor US', disabled: true, reason: 'Disabled — Cloudflare IP blocking' },
]

function JobsTable({ jobs }) {
  if (!jobs || jobs.length === 0) return null
  return (
    <table className="jobs-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Company</th>
          <th>Location</th>
          <th>Source</th>
          <th>Score</th>
          <th>Link</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((job, i) => (
          <tr key={i}>
            <td>{job.title}</td>
            <td>{job.company}</td>
            <td>{job.location}</td>
            <td><span className={`badge ${(job.source || '').toLowerCase()}`}>{job.source}</span></td>
            <td>{job.match_score ? `${Math.round(job.match_score * 100)}%` : '-'}</td>
            <td>
              {job.source_url ? (
                <a href={job.source_url} target="_blank" rel="noopener noreferrer">Open</a>
              ) : '-'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ToolUseCard({ tool }) {
  return (
    <div className="tool-use">
      <span className="tool-name">{tool.name || 'tool'}</span>
      <span className="tool-status"> — {tool.status || 'running'}</span>
      {tool.result && <div className="tool-result">{tool.result}</div>}
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div className="thinking">
      <span>Thinking</span>
      <div className="dots">
        <div className="dot"></div>
        <div className="dot"></div>
        <div className="dot"></div>
      </div>
    </div>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  return (
    <div className={`message ${isUser ? 'user' : 'ai'}`}>
      <div className="bubble">
        {!isUser && <div className="sender">AI Agent</div>}
        <div className="content">{message.content}</div>
        {message.tool_uses && message.tool_uses.map((tool, i) => (
          <ToolUseCard key={i} tool={tool} />
        ))}
        {message.jobs && <JobsTable jobs={message.jobs} />}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [resumeText, setResumeText] = useState('')
  const [fileName, setFileName] = useState('')
  const [settings, setSettings] = useState({
    keywords: '',
    location: 'Hyderabad',
    target: 20,
    experience: 'fresher',
    portals: ['naukri', 'indeed', 'linkedin'],
  })
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setFileName(file.name)

    if (file.type === 'text/plain') {
      const text = await file.text()
      setResumeText(text)
    } else {
      const formData = new FormData()
      formData.append('file', file)
      try {
        const resp = await fetch(`${API}/resume/parse`, { method: 'POST', body: formData })
        if (resp.ok) {
          const data = await resp.json()
          setResumeText(data.text || '')
        }
      } catch (err) {
        console.error('Resume parse error:', err)
      }
    }
  }

  const togglePortal = (portal) => {
    // Don't allow selecting disabled portals
    const portalDef = PORTALS.find(p => p.value === portal)
    if (portalDef?.disabled) return

    setSettings(prev => ({
      ...prev,
      portals: prev.portals.includes(portal)
        ? prev.portals.filter(p => p !== portal)
        : [...prev.portals, portal],
    }))
  }

  const sendMessage = async (text) => {
    const msg = text || input.trim()
    if (!msg || loading) return
    setInput('')

    const userMsg = { role: 'user', content: msg }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const resp = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          resume_text: resumeText,
          user_id: 'default_user',
          settings: {
            keywords: settings.keywords,
            location: settings.location,
            target_job_count: settings.target,
            experience_level: settings.experience,
            portals: settings.portals,
          },
        }),
      })

      if (resp.ok) {
        const data = await resp.json()
        const aiMsg = {
          role: 'assistant',
          content: data.response || 'Done.',
          tool_uses: data.tool_uses || [],
          jobs: data.jobs || [],
        }
        setMessages(prev => [...prev, aiMsg])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Failed to get response.' }])
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat-layout">
      {/* Sidebar */}
      <div className="sidebar">
        <h2>Resume</h2>
        <div className="file-upload" onClick={() => fileInputRef.current?.click()}>
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" onChange={handleFileUpload} />
          <div className="icon">{fileName ? '📄' : '📁'}</div>
          <div className="text">{fileName || 'Upload Resume (PDF/DOCX/TXT)'}</div>
        </div>

        <textarea
          placeholder="Or paste resume text here..."
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
        />

        <div className="divider"></div>

        <label>Keywords</label>
        <input type="text" value={settings.keywords} onChange={(e) => setSettings({...settings, keywords: e.target.value})} placeholder="e.g. Python, Java, Data Analyst" />

        <label>Location</label>
        <input type="text" value={settings.location} onChange={(e) => setSettings({...settings, location: e.target.value})} />

        <label>Target Jobs</label>
        <input type="number" value={settings.target} onChange={(e) => setSettings({...settings, target: parseInt(e.target.value) || 20})} min={1} max={100} />

        <label>Experience</label>
        <select value={settings.experience} onChange={(e) => setSettings({...settings, experience: e.target.value})}>
          <option value="fresher">Fresher</option>
          <option value="experienced">Experienced</option>
        </select>

        <div className="divider"></div>
        <label style={{ marginBottom: 8 }}>Portals</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {PORTALS.map(p => (
            <label
              key={p.value}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
                color: p.disabled ? '#666' : '#ccc',
                cursor: p.disabled ? 'not-allowed' : 'pointer',
                opacity: p.disabled ? 0.5 : 1,
              }}
              title={p.disabled ? p.reason : ''}
            >
              <input
                type="checkbox"
                checked={settings.portals.includes(p.value)}
                onChange={() => togglePortal(p.value)}
                disabled={p.disabled}
              />
              {p.label}
              {p.disabled && <span style={{ fontSize: 10, color: '#ff6b6b' }}>(unavailable)</span>}
            </label>
          ))}
        </div>

        <div className="divider"></div>
        <div className={`status ${resumeText ? 'active' : ''}`}>
          {resumeText ? 'Resume loaded' : 'Resume not uploaded'}
        </div>
      </div>

      {/* Main Chat */}
      <div className="main">
        <div className="chat-header">
          <h1>Job AI Agent</h1>
          <a href="/dashboard" className="dashboard-link">Dashboard</a>
        </div>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <h2>What can I help you with?</h2>
              <p>Search for jobs, analyze your resume, or browse company career pages.</p>
              <div className="suggestions">
                <div className="suggestion" onClick={() => sendMessage('Find 20 Python developer jobs in Hyderabad')}>
                  <div className="title">Find Python jobs</div>
                  <div className="desc">Search Indeed, Naukri, LinkedIn</div>
                </div>
                <div className="suggestion" onClick={() => sendMessage('Analyze my resume and suggest improvements')}>
                  <div className="title">Analyze my resume</div>
                  <div className="desc">Get AI feedback on your resume</div>
                </div>
                <div className="suggestion" onClick={() => sendMessage('Search for data analyst jobs and apply to the best ones')}>
                  <div className="title">Search & apply</div>
                  <div className="desc">Full job search pipeline</div>
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}

          {loading && (
            <div className="message ai">
              <div className="bubble"><ThinkingIndicator /></div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <div className="input-container">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Message Job AI Agent..."
              rows={1}
            />
            <button className="send-btn" onClick={() => sendMessage()} disabled={loading || !input.trim()}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
            </button>
          </div>
          <div className="input-hint">AI can make mistakes. Verify important information.</div>
        </div>
      </div>
    </div>
  )
}
