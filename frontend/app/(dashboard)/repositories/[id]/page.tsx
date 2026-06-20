'use client'

import { useEffect, useState, use } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { MetricCard, EmptyState, StatusBadge } from '@/components/ui'
import Link from 'next/link'

interface Repository {
  id: string
  name: string
  full_name: string
  description: string
  language: string
  default_branch: string
  html_url: string
  connected_at: string
  sync_status: string
  settings: {
    auto_analyze: boolean
    notify_on_failure: boolean
    ai_analysis_enabled: boolean
  }
}

interface RepoStats {
  total_runs: number
  success_rate: number
  avg_duration: number
  failure_count: number
}

interface Run {
  id: string
  github_run_id: number
  name: string
  github_run_number: number
  status: string
  conclusion: string | null
  event: string
  head_branch: string
  created_at: string
}

export default function RepositoryDetailPage({ params: paramsPromise }: { params: Promise<{ id: string }> }) {
  const params = use(paramsPromise)
  const repoId = params.id
  const { data: repo, loading: loadingRepo, error: repoError } = useApi<Repository>(`/repos/${repoId}`)
  const { data: stats, loading: loadingStats } = useApi<RepoStats>(`/repos/${repoId}/stats`, [repoId])
  const { data: runs, loading: loadingRuns } = useApi<Run[]>(`/repos/${repoId}/runs`, [repoId])

  const [autoAnalyze, setAutoAnalyze] = useState(true)
  const [notifyOnFailure, setNotifyOnFailure] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const [syncing, setSyncing] = useState(false)

  async function handleSync() {
    setSyncing(true)
    try {
      const res = await apiFetch(`/repos/${repoId}/sync`, { method: 'POST' })
      if (!res.ok) throw new Error('Sync failed')
      alert('Sync triggered successfully! Latest runs are being imported.')
      window.location.reload()
    } catch (e: any) {
      alert(`Error syncing: ${e.message}`)
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    if (repo) {
      setAutoAnalyze(repo.settings?.auto_analyze ?? true)
      setNotifyOnFailure(repo.settings?.notify_on_failure ?? true)
    }
  }, [repo])

  async function saveSettings() {
    setUpdating(true)
    try {
      // Patch settings via config endpoint or repo endpoint if available
      // Note: we can mock or call PUT/PATCH on /repos/{id}/settings
      await apiFetch(`/repos/${repoId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          settings: {
            auto_analyze: autoAnalyze,
            notify_on_failure: notifyOnFailure,
            ai_analysis_enabled: true
          }
        })
      })
      alert('Settings updated successfully!')
    } catch (e: any) {
      alert(`Error updating settings: ${e.message}`)
    } finally {
      setUpdating(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm('Are you sure you want to disconnect this repository? Historical run data will be retained but no new runs will be processed.')) {
      return
    }
    setDisconnecting(true)
    try {
      const res = await apiFetch(`/repos/${repoId}/disconnect`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Failed to disconnect repository')
      window.location.href = '/repositories'
    } catch (e: any) {
      alert(`Error: ${e.message}`)
      setDisconnecting(false)
    }
  }

  if (loadingRepo) {
    return (
      <>
        <Topbar title="Repository Details" />
        <main className="page-content">
          <div className="skeleton" style={{ height: 200, width: '100%', marginBottom: 24 }} />
          <div className="grid grid-3" style={{ marginBottom: 24 }}>
            <div className="skeleton" style={{ height: 100 }} />
            <div className="skeleton" style={{ height: 100 }} />
            <div className="skeleton" style={{ height: 100 }} />
          </div>
        </main>
      </>
    )
  }

  if (repoError || !repo) {
    return (
      <>
        <Topbar title="Error" />
        <main className="page-content">
          <EmptyState
            title="Repository Not Found"
            description="The requested repository could not be loaded or you do not have permission to view it."
          />
        </main>
      </>
    )
  }

  return (
    <>
      <Topbar title={`${repo.full_name}`} />
      <main className="page-content">
        {/* Repo header card */}
        <div className="card" style={{ padding: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <span className="badge badge-success">{repo.sync_status}</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Branch: {repo.default_branch}</span>
              </div>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', margin: '0 0 16px 0' }}>
                {repo.description || 'No description provided.'}
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <a href={repo.html_url} target="_blank" rel="noopener noreferrer" className="btn btn-outline btn-sm">
                  View on GitHub
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginLeft: 6 }}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
                <button className="btn btn-primary btn-sm" onClick={handleSync} disabled={syncing}>
                  {syncing ? 'Syncing...' : 'Sync Actions Runs'}
                </button>
              </div>
            </div>

            <button className="btn btn-outline" style={{ borderColor: 'var(--color-error)', color: 'var(--color-error)' }} onClick={handleDisconnect} disabled={disconnecting}>
              {disconnecting ? 'Disconnecting...' : 'Disconnect Repo'}
            </button>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-3" style={{ marginBottom: 'var(--space-6)' }}>
          <MetricCard
            label="Total Synced Runs"
            value={stats ? stats.total_runs : 0}
            loading={loadingStats}
          />
          <MetricCard
            label="Build Success Rate"
            value={stats ? `${Math.round(stats.success_rate * 100)}%` : '0%'}
            loading={loadingStats}
            variant={stats && stats.success_rate > 0.8 ? 'success' : 'warning'}
          />
          <MetricCard
            label="Avg Duration"
            value={stats ? `${Math.round(stats.avg_duration)}s` : '0s'}
            loading={loadingStats}
          />
        </div>

        {/* Split Section: Settings & Runs */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 'var(--space-6)' }}>
          {/* Settings panel */}
          <div className="card" style={{ padding: 'var(--space-6)', height: 'fit-content' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Pipeline Configuration
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                  <input
                    type="checkbox"
                    checked={autoAnalyze}
                    onChange={e => setAutoAnalyze(e.target.checked)}
                    style={{ accentColor: 'var(--color-accent)' }}
                  />
                  Auto-Analyze Failures
                </label>
                <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginLeft: 24, marginTop: 4 }}>
                  Instantly trigger AI Root Cause Analysis when a workflow run fails.
                </p>
              </div>

              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                  <input
                    type="checkbox"
                    checked={notifyOnFailure}
                    onChange={e => setNotifyOnFailure(e.target.checked)}
                    style={{ accentColor: 'var(--color-accent)' }}
                  />
                  Failure Notifications
                </label>
                <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginLeft: 24, marginTop: 4 }}>
                  Send alert notifications to Slack, Teams, and Email on failures.
                </p>
              </div>

              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 8 }} onClick={saveSettings} disabled={updating}>
                {updating ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>

          {/* Runs panel */}
          <div className="card" style={{ padding: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Recent Runs
            </h3>

            {loadingRuns ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="skeleton" style={{ height: 40 }} />
                <div className="skeleton" style={{ height: 40 }} />
                <div className="skeleton" style={{ height: 40 }} />
              </div>
            ) : runs && runs.length > 0 ? (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Run #</th>
                      <th>Workflow</th>
                      <th>Branch</th>
                      <th>Status</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => (
                      <tr key={run.id}>
                        <td>
                          <Link href={`/runs/${run.id}`} style={{ fontWeight: 600, color: 'var(--color-accent)', textDecoration: 'underline' }}>
                            #{run.github_run_number}
                          </Link>
                        </td>
                        <td>{run.name}</td>
                        <td className="font-mono text-xs">{run.head_branch}</td>
                        <td>
                          <StatusBadge conclusion={run.conclusion} status={run.status} />
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
                          {new Date(run.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No Runs Synced"
                description="This repository has no synced pipeline runs yet. Trigger a run on GitHub to see it here."
              />
            )}
          </div>
        </div>
      </main>
    </>
  )
}
