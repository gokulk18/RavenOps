'use client'

import { useEffect, useState, use } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { EmptyState, StatusBadge } from '@/components/ui'
import Link from 'next/link'

interface RunDetail {
  id: string
  name: string
  github_run_number: number
}

interface Job {
  id: string
  name: string
  status: string
  conclusion: string | null
  started_at: string
}

interface LogPageResponse {
  lines: string[]
  total_lines: number
  page: number
  per_page: number
  has_more: boolean
}

interface SearchResponse {
  matches: Array<{ line_number: number; content: string }>
  total_matches: number
}

export default function LogViewerPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = use(paramsPromise)
  const runId = params.id

  const { data: run } = useApi<RunDetail>(`/runs/${runId}`)
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [loadingJobs, setLoadingJobs] = useState(false)

  const [logLines, setLogLines] = useState<string[]>([])
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [logsError, setLogsError] = useState('')

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ line_number: number; content: string }>>([])
  const [searching, setSearching] = useState(false)

  // Fetch jobs
  useEffect(() => {
    setLoadingJobs(true)
    apiFetch(`/runs/${runId}/jobs`)
      .then(r => r.json())
      .then(data => {
        setJobs(data.jobs || [])
        // Auto-select the first job or the failed one
        const failedJob = data.jobs?.find((j: Job) => j.conclusion === 'failure')
        const defaultJob = failedJob || data.jobs?.[0]
        if (defaultJob) {
          setSelectedJobId(defaultJob.id)
        }
      })
      .finally(() => setLoadingJobs(false))
  }, [runId])

  // Fetch log lines
  useEffect(() => {
    if (!selectedJobId) return
    setLoadingLogs(true)
    setLogsError('')
    setLogLines([])
    setSearchResults([])
    setSearchQuery('')

    // Fetch logs from log-service via proxy
    apiFetch(`/logs/${runId}/pages?page=1&per_page=1500`)
      .then(res => {
        if (!res.ok) {
          throw new Error('Logs are not available for this run yet.')
        }
        return res.json()
      })
      .then((data: LogPageResponse) => {
        setLogLines(data.lines || [])
      })
      .catch((e: any) => {
        setLogsError(e.message)
      })
      .finally(() => {
        setLoadingLogs(false)
      })
  }, [runId, selectedJobId])

  // Handle Search
  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const res = await apiFetch(`/logs/${runId}/search?q=${encodeURIComponent(searchQuery)}`)
      if (res.ok) {
        const data: SearchResponse = await res.json()
        setSearchResults(data.matches || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  // Format log lines with ansi colors/group markers
  function formatLine(line: string) {
    // Strips timestamp if present
    const cleanLine = line.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+/, '')

    if (cleanLine.startsWith('##[group]')) {
      return (
        <span style={{ color: 'var(--color-accent)', fontWeight: 700 }}>
          ▶ {cleanLine.replace('##[group]', '')}
        </span>
      )
    }
    if (cleanLine.startsWith('##[endgroup]')) {
      return <span style={{ color: 'var(--color-text-tertiary)', fontSize: 10 }}>└─ group end</span>
    }
    if (cleanLine.startsWith('##[error]')) {
      return (
        <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>
          ✖ {cleanLine.replace('##[error]', '')}
        </span>
      )
    }
    if (cleanLine.includes('npm ERR!') || cleanLine.includes('Error:') || cleanLine.includes('FAIL')) {
      return <span style={{ color: '#EF4444' }}>{cleanLine}</span>
    }
    if (cleanLine.includes('npm warn') || cleanLine.includes('Warning:')) {
      return <span style={{ color: 'var(--color-warning)' }}>{cleanLine}</span>
    }
    return <span>{cleanLine}</span>
  }

  return (
    <>
      <Topbar title={run ? `${run.name} #${run.github_run_number} logs` : 'Workflow Logs'} />
      <main className="page-content" style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 'var(--space-6)', height: 'calc(100vh - var(--topbar-height) - 48px)', padding: 0 }}>
        {/* Jobs List Sidebar */}
        <div style={{ background: 'var(--color-bg-surface)', borderRight: '1px solid var(--color-border)', padding: 'var(--space-4)', overflowY: 'auto' }}>
          <h3 style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-secondary)', textTransform: 'uppercase', marginBottom: 'var(--space-3)' }}>
            Jobs in Run
          </h3>
          {loadingJobs ? (
            <div className="skeleton" style={{ height: 100 }} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {jobs.map(job => (
                <button
                  key={job.id}
                  onClick={() => setSelectedJobId(job.id)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: 6,
                    background: job.id === selectedJobId ? 'var(--color-bg-base)' : 'transparent',
                    border: '1px solid',
                    borderColor: job.id === selectedJobId ? 'var(--color-border)' : 'transparent',
                    color: job.id === selectedJobId ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                    textAlign: 'left',
                    fontSize: 'var(--text-sm)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8
                  }}
                >
                  <StatusBadge conclusion={job.conclusion} status={job.status} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Log Terminal area */}
        <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%', padding: 'var(--space-4)' }}>
          {/* Log Search box */}
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: 10, marginBottom: 'var(--space-4)' }}>
            <input
              type="text"
              placeholder="Search terms in terminal output..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{ flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-surface)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
            />
            <button type="submit" className="btn btn-outline" disabled={searching}>
              {searching ? 'Searching...' : 'Search'}
            </button>
            {searchQuery && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  setSearchQuery('')
                  setSearchResults([])
                }}
              >
                Clear
              </button>
            )}
          </form>

          {/* Search Result Matches */}
          {searchResults.length > 0 && (
            <div style={{ background: 'var(--color-bg-surface)', border: '1px solid var(--color-border)', borderRadius: 6, padding: 'var(--space-3)', marginBottom: 'var(--space-4)', maxHeight: 120, overflowY: 'auto' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-accent)', marginBottom: 6 }}>
                FOUND {searchResults.length} MATCHES:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {searchResults.map((match, idx) => (
                  <div key={idx} style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>
                    <span style={{ color: 'var(--color-text-tertiary)', marginRight: 8 }}>Line {match.line_number}:</span>
                    {match.content}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Terminal Box */}
          <div style={{ flex: 1, background: '#070708', border: '1px solid var(--color-border)', borderRadius: 8, padding: 'var(--space-4)', overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6, color: '#D4D4D8' }}>
            {loadingLogs ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="skeleton" style={{ height: 16, width: '40%' }} />
                <div className="skeleton" style={{ height: 16, width: '60%' }} />
                <div className="skeleton" style={{ height: 16, width: '50%' }} />
              </div>
            ) : logsError ? (
              <EmptyState
                title="Logs Unavailable"
                description={logsError}
                action={
                  <Link href={`/runs/${runId}`} className="btn btn-primary btn-sm">
                    Back to Details
                  </Link>
                }
              />
            ) : logLines.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {logLines.map((line, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: 16 }}>
                    <span style={{ width: 40, color: 'var(--color-text-tertiary)', textAlign: 'right', userSelect: 'none', flexShrink: 0 }}>
                      {idx + 1}
                    </span>
                    <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                      {formatLine(line)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Log Stream Empty"
                description="No console output recorded for this job."
              />
            )}
          </div>
        </div>
      </main>
    </>
  )
}
