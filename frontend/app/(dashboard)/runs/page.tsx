'use client'

import { useState, useEffect } from 'react'
import Topbar from '@/components/Topbar'
import { useApi } from '@/lib/utils'
import { EmptyState, StatusBadge } from '@/components/ui'
import Link from 'next/link'

interface Run {
  id: string
  github_run_id: number
  name: string
  github_run_number: number
  status: string
  conclusion: string | null
  event: string
  head_branch: string
  head_commit: {
    message: string
    author: { name: string }
  }
  created_at: string
  duration_seconds: number | null
  repo_name?: string
  repository?: {
    full_name: string
  }
}

interface Repository {
  id: string
  full_name: string
}

interface ReposResponse {
  repos: Repository[]
}

interface RunsResponse {
  runs: Run[]
  total: number
  page: number
  per_page: number
}

export default function RunsPage() {
  const [repoId, setRepoId] = useState('')
  const [conclusion, setConclusion] = useState('')
  const [branch, setBranch] = useState('')
  const [page, setPage] = useState(1)

  // Fetch repos for filter dropdown
  const { data: reposData } = useApi<ReposResponse>('/repos')

  // Build runs path with query params
  const buildQueryPath = () => {
    const params = new URLSearchParams()
    if (repoId) params.append('repo_id', repoId)
    if (conclusion) params.append('conclusion', conclusion)
    if (branch) params.append('branch', branch)
    params.append('page', String(page))
    params.append('per_page', '15')
    return `/runs?${params.toString()}`
  }

  const { data: runsData, loading, error } = useApi<RunsResponse>(buildQueryPath(), [repoId, conclusion, branch, page])

  // Reset page when filters change
  useEffect(() => {
    setPage(1)
  }, [repoId, conclusion, branch])

  const totalPages = runsData ? Math.ceil(runsData.total / runsData.per_page) : 1

  return (
    <>
      <Topbar title="Pipeline Runs" />
      <main className="page-content">
        {/* Filters Panel */}
        <div className="card" style={{ padding: 'var(--space-4) var(--space-6)', marginBottom: 'var(--space-6)', display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 200px' }}>
            <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>
              Repository
            </label>
            <select
              value={repoId}
              onChange={e => setRepoId(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
            >
              <option value="">All Repositories</option>
              {reposData?.repos?.map(repo => (
                <option key={repo.id} value={repo.id}>{repo.full_name}</option>
              ))}
            </select>
          </div>

          <div style={{ flex: '1 1 150px' }}>
            <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>
              Conclusion
            </label>
            <select
              value={conclusion}
              onChange={e => setConclusion(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
            >
              <option value="">All Outcomes</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="cancelled">Cancelled</option>
              <option value="skipped">Skipped</option>
              <option value="timed_out">Timed Out</option>
            </select>
          </div>

          <div style={{ flex: '1 1 150px' }}>
            <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>
              Branch
            </label>
            <input
              type="text"
              placeholder="e.g. main, dev"
              value={branch}
              onChange={e => setBranch(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
            />
          </div>

          <div style={{ alignSelf: 'flex-end', marginLeft: 'auto' }}>
            <button
              className="btn btn-outline btn-sm"
              onClick={() => {
                setRepoId('')
                setConclusion('')
                setBranch('')
                setPage(1)
              }}
            >
              Clear Filters
            </button>
          </div>
        </div>

        {/* Runs List Table */}
        <div className="card" style={{ padding: 'var(--space-6)' }}>
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="skeleton" style={{ height: 48 }} />
              <div className="skeleton" style={{ height: 48 }} />
              <div className="skeleton" style={{ height: 48 }} />
            </div>
          ) : runsData && runsData.runs.length > 0 ? (
            <>
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Workflow & Run #</th>
                      <th>Repository</th>
                      <th>Commit Details</th>
                      <th>Trigger</th>
                      <th>Outcome</th>
                      <th>Duration</th>
                      <th>Started</th>
                      <th style={{ textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runsData.runs.map(run => (
                      <tr key={run.id} className="hover-scale">
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
                            {run.name} #{run.github_run_number}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                            Branch: <span className="font-mono text-xs">{run.head_branch}</span>
                          </div>
                        </td>
                        <td>
                          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                            {run.repository?.full_name || 'unknown/repo'}
                          </span>
                        </td>
                        <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)' }}>
                            {run.head_commit?.message || 'No commit message'}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                            by {run.head_commit?.author?.name || 'unknown'}
                          </div>
                        </td>
                        <td style={{ textTransform: 'capitalize', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                          {run.event}
                        </td>
                        <td>
                          <StatusBadge conclusion={run.conclusion} status={run.status} />
                        </td>
                        <td style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                          {run.duration_seconds ? `${Math.floor(run.duration_seconds / 60)}m ${run.duration_seconds % 60}s` : '—'}
                        </td>
                        <td style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                          {new Date(run.created_at).toLocaleString()}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <Link href={`/runs/${run.id}`} className="btn btn-outline btn-sm">
                            Inspect
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'var(--space-6)', borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-4)' }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    Showing page {page} of {totalPages} ({runsData.total} total runs)
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      className="btn btn-outline btn-sm"
                      disabled={page === 1}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                    >
                      Previous
                    </button>
                    <button
                      className="btn btn-outline btn-sm"
                      disabled={page === totalPages}
                      onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <EmptyState
              title="No Runs Match the Query"
              description="Adjust your filters to locate the pipeline executions you are seeking."
            />
          )}
        </div>
      </main>
    </>
  )
}
