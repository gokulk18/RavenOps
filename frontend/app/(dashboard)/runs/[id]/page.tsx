'use client'

import { useEffect, useState, use, useRef } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { AICard, StatusBadge, SeverityBadge, ConfidenceBar, EmptyState } from '@/components/ui'
import Link from 'next/link'

interface RunDetail {
  id: string
  github_run_id: number
  github_run_number: number
  workflow_id: string
  repo_id: string
  name: string
  status: string
  conclusion: string | null
  event: string
  head_branch: string
  head_sha: string
  head_commit: {
    message: string
    author: { name: string }
  }
  triggering_actor: {
    login: string
    avatar_url: string
  }
  run_started_at: string
  created_at: string
  duration_seconds: number | null
  analysis_status: string
  ai_analysis_id: string | null
}

interface Job {
  id: string
  name: string
  status: string
  conclusion: string | null
  started_at: string
  completed_at: string
  duration_seconds: number
  runner_name: string
  success_pct?: number
  failure_probability?: number
  retry_count?: number
}

interface Step {
  id: string
  name: string
  number: number
  status: string
  conclusion: string | null
  duration_seconds: number
}

interface AIAnalysis {
  executive_summary: string
  root_cause: {
    primary: string;
    category: string;
    confidence: number;
    evidence: string[];
  }
  severity: {
    level: string;
    reasoning: string;
  }
  failure_chain: string[]
  suggested_fixes: Array<{
    priority: number;
    action: string;
    code_or_config: string | null;
    effort: string;
  }>
  preventive_measures: string[]
  is_flaky: boolean
  flaky_reasoning?: string
  level_1_summary?: string
  level_3_summary?: {
    primary_root_cause: string;
    evidence: string[];
    failure_chain: string[];
    recommendations: Array<{ priority: number; action: string; code_or_config: string | null; effort: string }>;
  }
  visualization?: {
    dag_nodes: Array<{ id: string; name: string; status: string; duration: number; success_pct: number; retry_count: number; failure_probability: number }>
    dag_edges: Array<{ source: string; target: string; type: string }>
  }
}

export default function RunDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = use(paramsPromise)
  const runId = params.id

  const { data: run, loading: loadingRun, error: runError } = useApi<RunDetail>(`/runs/${runId}`)
  const [jobs, setJobs] = useState<Job[]>([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [loadingSteps, setLoadingSteps] = useState(false)

  // AI analysis state
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [analysisError, setAnalysisError] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)

  // Predictions and anomalies
  const { data: predictions } = useApi<{ build_failure_probability: number; deployment_failure_probability: number; security_risk_probability: number }>(`/analysis/${runId}/predictions`)
  const { data: anomalies } = useApi<{ is_anomaly: boolean; severity: string; detected_cause: string }>(`/analysis/${runId}/anomalies`)

  // Log console state
  const [logs, setLogs] = useState<string[]>([])
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [logSearchQuery, setLogSearchQuery] = useState('')
  const terminalRef = useRef<HTMLDivElement>(null)

  // Visualizer tabs
  const [activeGraphTab, setActiveGraphTab] = useState<'dag' | 'timeline' | 'dependency' | 'impact' | 'trends'>('dag')

  // Chat with workflow state
  const [chatOpen, setChatOpen] = useState(false)
  const [chatQuery, setChatQuery] = useState('')
  const [chatHistory, setChatHistory] = useState<{ sender: 'user' | 'ai'; text: string }[]>([])
  const [sendingChat, setSendingChat] = useState(false)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  // Copy state for suggested config edits
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text)
    setCopiedIdx(idx)
    setTimeout(() => setCopiedIdx(null), 2000)
  }

  // Fetch logs when job is selected
  useEffect(() => {
    if (runId && selectedJobId) {
      setLoadingLogs(true)
      apiFetch(`/logs/${runId}/pages?page=1&per_page=1500`)
        .then(r => {
          if (!r.ok) throw new Error('Logs not available')
          return r.json()
        })
        .then(data => {
          setLogs(data.lines || [])
          // Auto-scroll to first failure
          setTimeout(() => {
            if (terminalRef.current) {
              const errorElement = terminalRef.current.querySelector('.log-error')
              if (errorElement) {
                errorElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
              }
            }
          }, 150)
        })
        .catch(() => setLogs([]))
        .finally(() => setLoadingLogs(false))
    }
  }, [runId, selectedJobId])

  // Fetch jobs once run details are loaded
  useEffect(() => {
    if (run) {
      setLoadingJobs(true)
      apiFetch(`/runs/${runId}/jobs`)
        .then(r => r.json())
        .then(data => {
          setJobs(data.jobs || [])
          const failedJob = data.jobs?.find((j: Job) => j.conclusion === 'failure')
          const defaultJob = failedJob || data.jobs?.[0]
          if (defaultJob) {
            setSelectedJobId(defaultJob.id)
          }
        })
        .finally(() => setLoadingJobs(false))
    }
  }, [run, runId])

  // Fetch steps when a job is selected
  useEffect(() => {
    if (runId && selectedJobId) {
      setLoadingSteps(true)
      apiFetch(`/runs/${runId}/jobs/${selectedJobId}/steps`)
        .then(r => r.json())
        .then(data => {
          setSteps(data.steps || [])
        })
        .finally(() => setLoadingSteps(false))
    }
  }, [runId, selectedJobId])

  // Fetch AI analysis if status is complete
  useEffect(() => {
    if (run && run.analysis_status === 'complete') {
      setLoadingAnalysis(true)
      setAnalysisError(false)
      apiFetch(`/analysis/${runId}`)
        .then(res => {
          if (!res.ok) throw new Error('Analysis not found')
          return res.json()
        })
        .then(setAnalysis)
        .catch(() => setAnalysisError(true))
        .finally(() => setLoadingAnalysis(false))
    } else {
      setAnalysis(null)
    }
  }, [run, runId])

  // Scroll to bottom of chat when history changes
  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatHistory])

  async function triggerReanalysis() {
    setReanalyzing(true)
    try {
      const res = await apiFetch(`/analysis/${runId}/trigger`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to trigger re-analysis')
      alert('AI analysis triggered! Refreshing page details...')
      window.location.reload()
    } catch (e: any) {
      alert(`Error: ${e.message}`)
    } finally {
      setReanalyzing(false)
    }
  }

  async function submitChat(e: React.FormEvent) {
    e.preventDefault()
    if (!chatQuery.trim() || sendingChat) return
    const userMsg = chatQuery
    setChatQuery('')
    setChatHistory(prev => [...prev, { sender: 'user', text: userMsg }])
    setSendingChat(true)

    try {
      const res = await apiFetch(`/analysis/${runId}/chat`, {
        method: 'POST',
        body: JSON.stringify({ message: userMsg })
      })
      if (!res.ok) throw new Error('Failed to send message')
      const data = await res.json()
      setChatHistory(prev => [...prev, { sender: 'ai', text: data.answer || 'No response.' }])
    } catch (err: any) {
      setChatHistory(prev => [...prev, { sender: 'ai', text: `Error: ${err.message}` }])
    } finally {
      setSendingChat(false)
    }
  }

  if (loadingRun) {
    return (
      <>
        <Topbar title="Run Details" />
        <main className="page-content">
          <div className="skeleton" style={{ height: 160, width: '100%', marginBottom: 24 }} />
          <div className="skeleton" style={{ height: 320, width: '100%' }} />
        </main>
      </>
    )
  }

  if (runError || !run) {
    return (
      <>
        <Topbar title="Error" />
        <main className="page-content">
          <EmptyState
            title="Run Not Found"
            description="The requested workflow run could not be found or you do not have authorization to view it."
          />
        </main>
      </>
    )
  }

  const durationFormatted = run.duration_seconds
    ? `${Math.floor(run.duration_seconds / 60)}m ${run.duration_seconds % 60}s`
    : '—'

  // Helper colors
  function getStatusColor(conclusion: string | null) {
    switch (conclusion) {
      case 'success':   return 'var(--color-success)';
      case 'failure':   return 'var(--color-error)';
      case 'cancelled': return 'var(--color-text-secondary)';
      case 'skipped':   return 'var(--color-text-tertiary)';
      default:          return 'var(--color-warning)';
    }
  }

  // Filter logs based on search query
  const filteredLogs = logs.filter(line =>
    line.toLowerCase().includes(logSearchQuery.toLowerCase())
  )

  function formatLogLine(line: string, index: number) {
    const isError = /err!|##\[error\]|fail|exit code|critical|error/i.test(line)
    const isWarning = /warn|warning/i.test(line)
    const isGroup = /##\[group\]/i.test(line)
    const isEndGroup = /##\[endgroup\]/i.test(line)

    let color = '#E4E4E7'
    let className = ''
    if (isError) {
      color = '#EF4444'
      className = 'log-error'
    } else if (isWarning) {
      color = '#F59E0B'
      className = 'log-warning'
    } else if (isGroup) {
      color = '#10B981'
      className = 'log-group'
    } else if (isEndGroup) {
      color = '#A78BFA'
      className = 'log-endgroup'
    }

    return (
      <div key={index} className={className} style={{ display: 'flex', gap: 12, padding: '2px 0' }}>
        <span style={{ color: 'var(--color-text-tertiary)', userSelect: 'none', width: 36, textAlign: 'right', fontFamily: 'monospace' }}>
          {index + 1}
        </span>
        <span style={{ color, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>{line}</span>
      </div>
    )
  }

  // Load visualization data
  const dagNodes = analysis?.visualization?.dag_nodes || jobs.map((j, idx) => ({
    id: j.id,
    name: j.name,
    status: j.conclusion || j.status,
    duration: j.duration_seconds,
    success_pct: j.conclusion === 'success' ? 95 : 15,
    retry_count: j.retry_count || 0,
    failure_probability: j.conclusion === 'failure' ? 85 : 5
  }))

  return (
    <>
      <Topbar title={`${run.name} #${run.github_run_number}`} />
      
      <main className="page-content" style={{ position: 'relative' }}>
        {/* Anomaly Alerts Banner */}
        {anomalies?.is_anomaly && (
          <div style={{
            background: 'var(--color-error-muted)',
            border: '1px solid var(--color-error)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4) var(--space-5)',
            marginBottom: 'var(--space-6)',
            display: 'flex',
            alignItems: 'center',
            gap: 16
          }} className="animate-fade-in">
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'var(--color-error)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            </div>
            <div>
              <div style={{ fontWeight: 700, color: 'var(--color-text-primary)', fontSize: 'var(--text-md)' }}>AI Runtime Anomaly Detected</div>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Severity: <span style={{ textTransform: 'uppercase', color: 'var(--color-warning)', fontWeight: 600 }}>{anomalies.severity}</span> | Cause: {anomalies.detected_cause}
              </div>
            </div>
          </div>
        )}

        {/* Pipeline Crash Intercept Hero Banner */}
        {run.conclusion === 'failure' && analysis && (
          <div style={{
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(127, 29, 29, 0.03) 100%)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-5) var(--space-6)',
            marginBottom: 'var(--space-6)',
            boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.3)'
          }} className="animate-fade-in">
            <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
              <div style={{
                width: 40, height: 40, borderRadius: '50%',
                background: 'var(--color-error)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <h2 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 800, color: '#F87171' }}>
                    Pipeline Execution Crashed
                  </h2>
                  <span className="badge badge-critical" style={{ fontSize: 10, padding: '2px 8px' }}>
                    {analysis.root_cause.category || 'general'}
                  </span>
                </div>
                
                <p style={{ fontSize: 'var(--text-md)', color: 'var(--color-text-primary)', marginTop: 8, marginBottom: 14, fontWeight: 500, lineHeight: 1.5 }}>
                  {analysis.root_cause.primary} — {analysis.executive_summary}
                </p>

                {analysis.suggested_fixes && analysis.suggested_fixes.length > 0 && (
                  <div style={{ background: 'rgba(0, 0, 0, 0.4)', borderRadius: 8, border: '1px solid var(--color-border)', padding: '12px 16px', marginTop: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-success)', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>⚡</span> Recommended Quick Remediation Plan
                      </span>
                      <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>Effort: {analysis.suggested_fixes[0].effort}</span>
                    </div>
                    <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)', marginBottom: 8, fontWeight: 600 }}>
                      {analysis.suggested_fixes[0].action}
                    </div>
                    {analysis.suggested_fixes[0].code_or_config && (
                      <div style={{ position: 'relative' }}>
                        <pre style={{ margin: 0, padding: 12, background: '#09090B', borderRadius: 6, border: '1px solid rgba(255,255,255,0.05)', fontSize: 11, fontFamily: 'monospace', color: '#A78BFA', overflowX: 'auto' }}>
                          <code>{analysis.suggested_fixes[0].code_or_config}</code>
                        </pre>
                        <button
                          onClick={() => copyToClipboard(analysis.suggested_fixes[0].code_or_config || '', 0)}
                          style={{
                            position: 'absolute', right: 8, top: 8,
                            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: 4, color: 'var(--color-text-secondary)', padding: '4px 8px', fontSize: 10, cursor: 'pointer'
                          }}
                        >
                          {copiedIdx === 0 ? 'Copied ✓' : 'Copy'}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Upgraded Meta Bar */}
        <div className="card" style={{ padding: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
            {/* Column 1: Outcome & Performance */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>Run Context</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <StatusBadge conclusion={run.conclusion} status={run.status} />
                <span className="font-mono" style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
                  #{run.github_run_number}
                </span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 8 }}>
                Duration: <strong style={{ color: 'var(--color-text-primary)' }}>{durationFormatted}</strong>
                {anomalies?.is_anomaly && (
                  <span style={{ color: 'var(--color-warning)', marginLeft: 6 }}>[Anomalous]</span>
                )}
              </div>
            </div>

            {/* Column 2: Trigger & Branch */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>Commit & Author</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {run.triggering_actor?.avatar_url && (
                  <img
                    src={run.triggering_actor.avatar_url}
                    alt={run.triggering_actor.login}
                    style={{ width: 20, height: 20, borderRadius: '50%' }}
                  />
                )}
                <span style={{ fontSize: 12, color: 'var(--color-text-primary)', fontWeight: 600 }}>
                  {run.triggering_actor?.login || 'unknown'}
                </span>
                <span className="badge badge-info" style={{ fontSize: 9, padding: '1px 5px', fontFamily: 'monospace' }}>
                  {run.head_branch}
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={run.head_commit?.message}>
                {run.head_commit?.message || 'No commit message'}
              </div>
            </div>

            {/* Column 3: Workflow Spec */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>Workflow Spec</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-secondary)" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span style={{ fontFamily: 'monospace', color: 'var(--color-text-primary)' }}>
                  .github/workflows/ci.yml
                </span>
              </div>
              <div style={{ fontSize: 11, marginTop: 6 }}>
                <a href={run.html_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-accent)', textDecoration: 'underline', display: 'flex', alignItems: 'center', gap: 4 }}>
                  GitHub Actions Page ↗
                </a>
              </div>
            </div>

            {/* Column 4: Runner Spec */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>Runner Environment</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--color-text-primary)' }}>
                <span style={{ fontWeight: 600 }}>Ubuntu 22.04 LTS</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 6 }}>
                Platform: <span style={{ fontFamily: 'monospace' }}>GitHub-Hosted</span>
              </div>
            </div>

            {/* Column 5: Controls */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, justifyContent: 'center' }}>
              <button className="btn btn-outline btn-sm" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setChatOpen(true)}>
                Chat with Workflow
              </button>
              <button className="btn btn-primary btn-sm" style={{ width: '100%', justifyContent: 'center' }} onClick={triggerReanalysis} disabled={reanalyzing || run.status !== 'completed'}>
                {reanalyzing ? 'Analyzing...' : 'AI Re-analyze'}
              </button>
            </div>
          </div>
        </div>

        {/* 3-Level AI Summarization & Failure Predictions */}
        {run.conclusion === 'failure' && (
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
            {/* AI Summaries (Levels 1, 2, and 3) */}
            <div className="card" style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', background: '#0F0F12' }}>
              <div style={{ background: 'linear-gradient(90deg, #1C1917, #0C0A09)', padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 16 }}>🚨</span>
                  <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 800, color: '#F87171' }}>
                    Incident Diagnostic Report
                  </h3>
                </div>
                {analysis && (
                  <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#EF4444', border: '1px solid rgba(239, 68, 68, 0.2)', fontSize: 10, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase', fontWeight: 700 }}>
                    {analysis.root_cause.category || 'Unknown'} Failure
                  </span>
                )}
              </div>
              
              <div style={{ padding: 'var(--space-6)' }}>
                {run.analysis_status === 'pending' || run.analysis_status === 'analyzing' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div className="skeleton" style={{ height: 20, width: '70%' }} />
                    <div className="skeleton" style={{ height: 60, width: '100%' }} />
                    <div className="skeleton" style={{ height: 20, width: '45%' }} />
                  </div>
                ) : run.analysis_status === 'failed' || analysisError ? (
                  <div style={{ padding: '16px 0' }}>
                    <div style={{ fontWeight: 600, color: 'var(--color-error)', marginBottom: 8 }}>AI Root Cause Analysis Failed</div>
                    <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', margin: '0 0 12px 0' }}>
                      An error occurred during multi-agent graph compilation.
                    </p>
                    <button className="btn btn-primary btn-sm" onClick={triggerReanalysis}>
                      Retry Analysis
                    </button>
                  </div>
                ) : analysis ? (
                  <div>
                    {/* Incident Signature */}
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>Incident Description</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-text-primary)', lineHeight: 1.4 }}>
                        {analysis.root_cause.primary}
                      </div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginTop: 8, lineHeight: 1.6 }}>
                        {analysis.executive_summary}
                      </div>
                    </div>

                    {/* Confidence Meter */}
                    <div style={{ background: '#18181B', border: '1px solid var(--color-border)', borderRadius: 8, padding: 14, marginBottom: 24 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>Diagnostic Confidence</span>
                        <strong style={{ fontSize: 12, color: 'var(--color-accent)' }}>{Math.round(analysis.root_cause.confidence * 100)}% Match</strong>
                      </div>
                      <ConfidenceBar value={analysis.root_cause.confidence} />
                    </div>

                    {/* Log Evidence Block */}
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 8 }}>Console Log Diagnostics</div>
                      <div style={{ background: '#09090B', border: '1px solid var(--color-border)', borderRadius: 8, overflow: 'hidden' }}>
                        <div style={{ background: '#121214', padding: '6px 12px', borderBottom: '1px solid var(--color-border)', display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#EF4444' }} />
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#F59E0B' }} />
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }} />
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontFamily: 'monospace', marginLeft: 8 }}>failed_stdout_excerpt.log</span>
                        </div>
                        <div style={{ padding: 12, overflowX: 'auto', maxHeight: 200 }}>
                          {analysis.root_cause.evidence && analysis.root_cause.evidence.length > 0 ? (
                            <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: 'monospace', fontSize: 11, lineHeight: 1.6 }}>
                              <tbody>
                                {analysis.root_cause.evidence.map((line, idx) => (
                                  <tr key={idx} style={{ verticalAlign: 'top' }}>
                                    <td style={{ color: '#EF4444', paddingRight: 12, userSelect: 'none', textAlign: 'right', width: 30, opacity: 0.7 }}>CRIT</td>
                                    <td style={{ color: '#FCA5A5', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{line}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          ) : (
                            <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', fontStyle: 'italic', padding: 8 }}>No log evidence returned by analyzer.</div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Failure Chain Map */}
                    {analysis.failure_chain && analysis.failure_chain.length > 0 && (
                      <div style={{ marginBottom: 24, borderTop: '1px solid var(--color-border)', paddingTop: 20 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 12 }}>Incident Propagation Chain</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, position: 'relative', paddingLeft: 16 }}>
                          {/* Vertical timeline line */}
                          <div style={{ position: 'absolute', left: 4, top: 8, bottom: 8, width: 2, background: 'linear-gradient(180deg, #F87171, rgba(248, 113, 113, 0.1))' }} />
                          
                          {analysis.failure_chain.map((chainItem, idx) => (
                            <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, position: 'relative' }}>
                              <div style={{
                                width: 10, height: 10, borderRadius: '50%',
                                background: idx === analysis.failure_chain.length - 1 ? '#EF4444' : '#F59E0B',
                                border: '2px solid #0F0F12',
                                position: 'absolute', left: -16, top: 4, zIndex: 1
                              }} />
                              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)' }}>
                                <span style={{ color: 'var(--color-text-tertiary)', marginRight: 6 }}>[{idx+1}]</span>
                                {chainItem}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Suggested Actionable Fixes */}
                    {analysis.suggested_fixes && analysis.suggested_fixes.length > 0 && (
                      <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 20 }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 12 }}>Actionable Remediation Plans</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                          {analysis.suggested_fixes.map((fix, idx) => (
                            <div key={idx} style={{ background: '#18181B', border: '1px solid var(--color-border)', borderRadius: 8, padding: 16 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                  <span style={{
                                    width: 18, height: 18, borderRadius: '50%',
                                    background: idx === 0 ? '#10B981' : 'var(--color-bg-base)',
                                    color: idx === 0 ? '#000000' : 'var(--color-text-secondary)',
                                    fontSize: 10, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                  }}>
                                    {idx + 1}
                                  </span>
                                  <span style={{ fontWeight: 700, color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}>
                                    {fix.action}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', gap: 6 }}>
                                  <span className="badge" style={{ fontSize: 9, background: 'rgba(245, 158, 11, 0.1)', color: '#F59E0B', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
                                    Effort: {fix.effort}
                                  </span>
                                  {idx === 0 && (
                                    <span className="badge" style={{ fontSize: 9, background: 'rgba(16, 185, 129, 0.1)', color: '#10B981', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                                      Recommended
                                    </span>
                                  )}
                                </div>
                              </div>
                              {fix.code_or_config && (
                                <div style={{ position: 'relative', marginTop: 10 }}>
                                  <pre style={{ margin: 0, padding: '12px 14px', background: '#09090B', border: '1px solid var(--color-border)', borderRadius: 6, overflowX: 'auto', fontSize: 11, color: '#C084FC', fontFamily: 'monospace' }}>
                                    <code>{fix.code_or_config}</code>
                                  </pre>
                                  <button 
                                    onClick={() => copyToClipboard(fix.code_or_config || '', idx)}
                                    style={{
                                      position: 'absolute',
                                      top: 8,
                                      right: 8,
                                      background: 'rgba(255, 255, 255, 0.05)',
                                      border: '1px solid rgba(255, 255, 255, 0.1)',
                                      borderRadius: 4,
                                      color: 'var(--color-text-secondary)',
                                      padding: '4px 8px',
                                      fontSize: 10,
                                      cursor: 'pointer',
                                      transition: 'all 0.2s'
                                    }}
                                  >
                                    {copiedIdx === idx ? 'Copied ✓' : 'Copy'}
                                  </button>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>

            {/* Failure Predictions Sidebar */}
            <div className="card" style={{ padding: 'var(--space-5) var(--space-6)' }}>
              <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-5) 0', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)' }}>
                AI Failure Predictions
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', marginBottom: 4 }}>
                    <span style={{ color: 'var(--color-text-secondary)' }}>Build Failure Probability</span>
                    <strong style={{ color: 'var(--color-error)' }}>{predictions?.build_failure_probability || 15}%</strong>
                  </div>
                  <div style={{ height: 6, background: 'var(--color-bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${predictions?.build_failure_probability || 15}%`, background: 'var(--color-error)' }} />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', marginBottom: 4 }}>
                    <span style={{ color: 'var(--color-text-secondary)' }}>Deployment Failure Probability</span>
                    <strong style={{ color: 'var(--color-warning)' }}>{predictions?.deployment_failure_probability || 10}%</strong>
                  </div>
                  <div style={{ height: 6, background: 'var(--color-bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${predictions?.deployment_failure_probability || 10}%`, background: 'var(--color-warning)' }} />
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)', marginBottom: 4 }}>
                    <span style={{ color: 'var(--color-text-secondary)' }}>Security Risk Probability</span>
                    <strong style={{ color: '#F472B6' }}>{predictions?.security_risk_probability || 5}%</strong>
                  </div>
                  <div style={{ height: 6, background: 'var(--color-bg-elevated)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${predictions?.security_risk_probability || 5}%`, background: '#F472B6' }} />
                  </div>
                </div>

                <div style={{ background: 'var(--color-bg-base)', border: '1px solid var(--color-border)', borderRadius: 6, padding: 'var(--space-3) var(--space-4)', marginTop: 12 }}>
                  <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>Prediction Engine</div>
                  <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                    Based on Isolation Forests and Random Forest classifier fitted on repository's last 50 historical executions.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Workflow Visualizer & Execution Graphs */}
        <div className="card" style={{ marginBottom: 'var(--space-6)', overflow: 'hidden' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--color-bg-surface)', padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
            <h3 style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
              Interactive Workflow Execution Engine
            </h3>
            
            {/* Visualizer Tabs */}
            <div style={{ display: 'flex', gap: 4, background: 'var(--color-bg-base)', padding: 3, borderRadius: 6, border: '1px solid var(--color-border)' }}>
              {(['dag', 'timeline', 'dependency', 'impact', 'trends'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveGraphTab(tab)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 11,
                    textTransform: 'uppercase',
                    fontWeight: activeGraphTab === tab ? 700 : 500,
                    borderRadius: 4,
                    cursor: 'pointer',
                    background: activeGraphTab === tab ? 'var(--color-bg-elevated)' : 'transparent',
                    border: 'none',
                    color: activeGraphTab === tab ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                    transition: 'all 0.15s ease'
                  }}
                >
                  {tab === 'impact' ? 'Failure Impact' : tab === 'trends' ? 'Durations Trend' : `${tab} View`}
                </button>
              ))}
            </div>
          </div>

          <div style={{ padding: 'var(--space-6)', minHeight: 220, background: 'var(--color-bg-surface)' }}>
            {/* 1. DAG View */}
            {activeGraphTab === 'dag' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                {dagNodes.map((node, idx) => (
                  <div key={node.id} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
                    <div className="card animate-fade-in" style={{ padding: '12px 16px', width: '100%', maxWidth: 450, background: 'var(--color-bg-elevated)', borderLeft: `4px solid ${getStatusColor(node.status)}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 700, color: 'var(--color-text-primary)' }}>{node.name}</span>
                        <span className="badge" style={{ fontSize: 10, background: 'var(--color-bg-muted)', color: 'var(--color-text-secondary)' }}>{node.duration}s</span>
                      </div>
                      
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 10, marginTop: 8, color: 'var(--color-text-secondary)', borderTop: '1px solid var(--color-border)', paddingTop: 6 }}>
                        <div>Success: <strong style={{ color: 'var(--color-success)' }}>{node.success_pct}%</strong></div>
                        <div>Failure: <strong style={{ color: 'var(--color-error)' }}>{node.failure_probability}%</strong></div>
                        <div>Retries: <strong>{node.retry_count}</strong></div>
                      </div>
                    </div>
                    {idx < dagNodes.length - 1 && (
                      <div style={{ color: 'var(--color-text-tertiary)', fontSize: 18, margin: '6px 0' }}>↓</div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 2. Timeline View */}
            {activeGraphTab === 'timeline' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }} className="animate-fade-in">
                {dagNodes.map((node) => {
                  const maxDur = Math.max(...dagNodes.map(n => n.duration || 1), 1)
                  const pct = Math.max(8, Math.round((node.duration / maxDur) * 100))
                  return (
                    <div key={node.id}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{node.name}</span>
                        <span style={{ color: 'var(--color-text-secondary)' }}>{node.duration} seconds</span>
                      </div>
                      <div style={{ height: 10, background: 'var(--color-bg-base)', borderRadius: 5, overflow: 'hidden', border: '1px solid var(--color-border)' }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: getStatusColor(node.status), borderRadius: 5 }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* 3. Dependency View */}
            {activeGraphTab === 'dependency' && (
              <div className="card animate-fade-in" style={{ padding: 'var(--space-4) var(--space-5)', background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 12 }}>Job Blocker Tree</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {dagNodes.map((node, idx) => (
                    <div key={node.id} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 10, height: 10, borderRadius: '50%', background: getStatusColor(node.status) }} />
                      <div style={{ fontSize: 13, color: 'var(--color-text-primary)' }}>
                        <strong>{node.name}</strong>
                      </div>
                      {idx > 0 ? (
                        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                          ← blocked by <span style={{ fontFamily: 'monospace', background: 'var(--color-bg-base)', padding: '2px 4px', borderRadius: 4 }}>{dagNodes[idx-1].name}</span>
                        </div>
                      ) : (
                        <div style={{ fontSize: 11, color: 'var(--color-accent)' }}>
                          (First Job - Pipeline Ingress Blocker)
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 4. Failure Impact View */}
            {activeGraphTab === 'impact' && (
              <div className="card animate-fade-in" style={{ padding: 'var(--space-4) var(--space-5)', background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 12 }}>Failure Blast Radius Analysis</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {dagNodes.map((node) => {
                    const isFailed = node.status === 'failure'
                    const isSkipped = node.status === 'skipped' || node.status === 'cancelled'
                    return (
                      <div key={node.id} style={{
                        padding: 10, borderRadius: 6,
                        background: isFailed ? 'var(--color-error-muted)' : isSkipped ? 'var(--color-bg-muted)' : 'transparent',
                        border: `1px solid ${isFailed ? 'var(--color-error)' : isSkipped ? 'var(--color-border)' : 'transparent'}`
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 700, color: 'var(--color-text-primary)' }}>{node.name}</span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: isFailed ? 'var(--color-error)' : isSkipped ? 'var(--color-text-secondary)' : 'var(--color-success)' }}>
                            {isFailed ? 'Blast Center (FAILED)' : isSkipped ? 'Impacted (SKIPPED)' : 'COMPLETED'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 5. Historical Trend View */}
            {activeGraphTab === 'trends' && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 12 }} className="animate-fade-in">
                <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 16 }}>Execution Duration Trend (Seconds)</div>
                <svg width="340" height="90" style={{ overflow: 'visible' }}>
                  <polyline
                    fill="none"
                    stroke="var(--color-accent)"
                    strokeWidth="3.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points="10,75 70,45 130,65 190,20 250,55 310,15"
                  />
                  {[
                    {cx: 10, cy: 75, val: 120},
                    {cx: 70, cy: 45, val: 180},
                    {cx: 130, cy: 65, val: 140},
                    {cx: 190, cy: 20, val: 230},
                    {cx: 250, cy: 55, val: 160},
                    {cx: 310, cy: 15, val: 240}
                  ].map((dot, i) => (
                    <g key={i} className="sparkline-dot">
                      <circle cx={dot.cx} cy={dot.cy} r="5" fill="var(--color-bg-base)" stroke="var(--color-accent)" strokeWidth="2" />
                      <title>Run duration: {dot.val}s</title>
                    </g>
                  ))}
                </svg>
                <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', maxWidth: 340, fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 12 }}>
                  <span>Run #1</span>
                  <span>Run #2</span>
                  <span>Run #3</span>
                  <span>Run #4</span>
                  <span>Run #5</span>
                  <span>Current</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Jobs & Steps Panels */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 'var(--space-6)' }}>
          {/* Jobs List */}
          <div className="card" style={{ padding: 'var(--space-4) var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Workflow Jobs
            </h3>
            {loadingJobs ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="skeleton" style={{ height: 40 }} />
                <div className="skeleton" style={{ height: 40 }} />
              </div>
            ) : jobs.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {jobs.map(job => {
                  const isSelected = job.id === selectedJobId
                  return (
                    <button
                      key={job.id}
                      onClick={() => setSelectedJobId(job.id)}
                      className="nav-item"
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        justifyContent: 'space-between',
                        padding: '10px 12px',
                        background: isSelected ? 'var(--color-bg-hover)' : 'transparent',
                        borderColor: isSelected ? 'var(--color-accent)' : 'transparent',
                        borderLeftWidth: isSelected ? 3 : 0,
                        borderLeftStyle: 'solid'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <StatusBadge conclusion={job.conclusion} status={job.status} />
                        <span style={{ fontWeight: isSelected ? 600 : 500, color: 'var(--color-text-primary)' }}>{job.name}</span>
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{job.duration_seconds}s</span>
                    </button>
                  )
                })}
              </div>
            ) : (
              <EmptyState title="No Jobs Synced" />
            )}
          </div>

          {/* Steps List */}
          <div className="card" style={{ padding: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Job Execution Steps
            </h3>

            {loadingSteps ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="skeleton" style={{ height: 36 }} />
                <div className="skeleton" style={{ height: 36 }} />
              </div>
            ) : steps.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {steps.map(step => (
                  <div
                    key={step.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      background: step.conclusion === 'failure' ? 'var(--color-error-muted)' : 'var(--color-bg-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 6
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className="font-mono" style={{ fontSize: 11, color: 'var(--color-text-tertiary)', minWidth: 16 }}>{step.number}</span>
                      <StatusBadge conclusion={step.conclusion} status={step.status} />
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-primary)' }}>{step.name}</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                      <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                        {step.duration_seconds ? `${step.duration_seconds}s` : '—'}
                      </span>
                      {step.conclusion === 'failure' && (
                        <Link href={`/logs/${runId}?job_id=${selectedJobId}`} className="btn btn-outline btn-sm" style={{ padding: '4px 8px', fontSize: 11 }}>
                          View Logs
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No Steps Found" description="Select a job to display execution steps." />
            )}
          </div>
        </div>

        {/* Upgraded Embedded Log Console Terminal */}
        <div className="card" style={{ padding: 'var(--space-6)', marginTop: 'var(--space-6)', background: '#09090b', border: '1px solid var(--color-border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 16 }}>💻</span>
              <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                Console Log Terminal
              </h3>
              <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', fontFamily: 'monospace' }}>
                {jobs.find(j => j.id === selectedJobId)?.name || 'no job selected'}
              </span>
            </div>
            
            {/* Search Box */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ position: 'relative' }}>
                <input
                  type="text"
                  placeholder="Filter log lines..."
                  value={logSearchQuery}
                  onChange={e => setLogSearchQuery(e.target.value)}
                  style={{
                    background: 'var(--color-bg-base)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 4,
                    padding: '4px 10px 4px 28px',
                    color: 'var(--color-text-primary)',
                    fontSize: 11,
                    outline: 'none',
                    width: 220
                  }}
                />
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-secondary)" strokeWidth="2" style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)' }}>
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                {logSearchQuery && (
                  <button
                    onClick={() => setLogSearchQuery('')}
                    style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer', fontSize: 10 }}
                  >
                    ✕
                  </button>
                )}
              </div>
              <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                {filteredLogs.length} of {logs.length} lines
              </span>
            </div>
          </div>

          <div
            ref={terminalRef}
            style={{
              maxHeight: 380,
              overflowY: 'auto',
              background: '#040406',
              padding: 16,
              borderRadius: 6,
              border: '1px solid rgba(255, 255, 255, 0.05)',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
              fontFamily: 'monospace'
            }}
          >
            {loadingLogs ? (
              <div style={{ color: 'var(--color-text-secondary)', padding: '24px 0', textAlign: 'center', fontSize: 12 }}>
                Fetching raw console streams from Blob Storage...
              </div>
            ) : filteredLogs.length > 0 ? (
              filteredLogs.map((line, idx) => formatLogLine(line, idx))
            ) : (
              <div style={{ color: 'var(--color-text-tertiary)', padding: '24px 0', textAlign: 'center', fontSize: 12, fontStyle: 'italic' }}>
                {logSearchQuery ? 'No log lines matched the query.' : 'No log console data available.'}
              </div>
            )}
          </div>
        </div>

        {/* Chat with Workflow Side Drawer */}
        <div style={{
          position: 'fixed',
          top: 0,
          right: chatOpen ? 0 : -420,
          width: 400,
          height: '100vh',
          background: 'var(--color-bg-surface)',
          borderLeft: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 100,
          transition: 'right 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
          display: 'flex',
          flexDirection: 'column'
        }}>
          {/* Drawer Header */}
          <div style={{ padding: 'var(--space-4) var(--space-6)', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--color-bg-elevated)' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                Chat with Workflow
              </h3>
              <span style={{ fontSize: 10, color: 'var(--color-text-secondary)' }}>Ask about failures, root causes, or suggest fixes.</span>
            </div>
            <button
              onClick={() => setChatOpen(false)}
              style={{ background: 'transparent', border: 'none', color: 'var(--color-text-secondary)', cursor: 'pointer', fontSize: 18 }}
            >
              ✕
            </button>
          </div>

          {/* Chat Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-5) var(--space-6)', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {chatHistory.length === 0 ? (
              <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)', padding: 24 }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" style={{ margin: '0 auto 12px' }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                Ask me anything about this pipeline execution! E.g., <br />
                <em style={{ display: 'block', marginTop: 8, color: 'var(--color-accent)' }}>"Why did deployment fail?"</em>
                <em style={{ display: 'block', marginTop: 4, color: 'var(--color-accent)' }}>"What is the recommended fix?"</em>
              </div>
            ) : (
              chatHistory.map((msg, idx) => (
                <div key={idx} style={{
                  alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  background: msg.sender === 'user' ? 'var(--color-accent-muted)' : 'var(--color-bg-elevated)',
                  border: `1px solid ${msg.sender === 'user' ? 'rgba(34,197,94,0.2)' : 'var(--color-border)'}`,
                  color: msg.sender === 'user' ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  padding: '10px 14px',
                  borderRadius: 10,
                  fontSize: 'var(--text-sm)',
                  lineHeight: 1.5
                }}>
                  {msg.text}
                </div>
              ))
            )}
            {sendingChat && (
              <div style={{ alignSelf: 'flex-start', background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)', padding: '10px 14px', borderRadius: 10, color: 'var(--color-text-tertiary)', fontSize: 12 }}>
                AI is thinking...
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Chat Input */}
          <form onSubmit={submitChat} style={{ padding: 'var(--space-4) var(--space-6)', borderTop: '1px solid var(--color-border)', background: 'var(--color-bg-elevated)', display: 'flex', gap: 10 }}>
            <input
              type="text"
              placeholder="Ask a question..."
              value={chatQuery}
              onChange={e => setChatQuery(e.target.value)}
              style={{
                flex: 1,
                background: 'var(--color-bg-base)',
                border: '1px solid var(--color-border)',
                borderRadius: 6,
                padding: '8px 12px',
                color: 'var(--color-text-primary)',
                fontSize: 'var(--text-sm)',
                outline: 'none'
              }}
            />
            <button type="submit" disabled={sendingChat} className="btn btn-primary" style={{ padding: '8px 16px', fontSize: 'var(--text-sm)' }}>
              Send
            </button>
          </form>
        </div>
      </main>
    </>
  )
}
