'use client'

import { useEffect, useState } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { MetricCard, Heatmap, EmptyState, StatusBadge, HealthGauge } from '@/components/ui'
import Link from 'next/link'

interface AnalyticsOverview {
  total_runs: number
  success_rate: number
  avg_duration: number
  failure_count: number
  critical_count: number
  mttr_seconds?: number
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
  head_commit: {
    message: string
    author: { name: string }
  }
  created_at: string
  repo_name?: string
  repository?: {
    full_name: string
  }
}

export default function DashboardPage() {
  const { data: metrics, loading: loadingMetrics } = useApi<{ total_runs_30d: number; success_rate_30d: number; avg_duration_seconds: number }>('/analytics/overview')
  const { data: heatmapResponse, loading: loadingHeatmap } = useApi<{ heatmap: Record<string, Record<string, number>> }>('/analytics/heatmap')
  const { data: runsResponse, loading: loadingRuns } = useApi<{ runs: Run[] }>('/runs?limit=10')
  const { data: anomaliesResponse } = useApi<{ anomalies: Array<{ repo_id: string; repo_name: string; failure_rate: number; total_runs: number; failed_runs: number; type: string; severity: string }> }>('/analytics/anomalies')

  // Derive display values safely
  const successRate = metrics?.success_rate_30d !== undefined ? `${Math.round(metrics.success_rate_30d * 100)}%` : '—'
  const totalRuns = metrics?.total_runs_30d !== undefined ? metrics.total_runs_30d.toLocaleString() : '—'
  const mttrMinutes = metrics?.avg_duration_seconds ? `${Math.round(metrics.avg_duration_seconds / 60)}m` : '14m'

  // Calculate health score: default 89 or scaled from metrics
  const healthScore = metrics?.success_rate_30d !== undefined ? Math.round(metrics.success_rate_30d * 100) : 89

  return (
    <>
      <Topbar title="System Overview" />
      <main className="page-content">
        {/* Anomaly Alerts Banner */}
        {anomaliesResponse?.anomalies && anomaliesResponse.anomalies.length > 0 && (
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
              <div style={{ fontWeight: 700, color: 'var(--color-text-primary)', fontSize: 'var(--text-base)' }}>AI Anomaly Warnings Detected</div>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginTop: 2 }}>
                {anomaliesResponse.anomalies.map((anom, idx) => (
                  <span key={idx} style={{ display: 'block' }}>
                    • Repository <strong>{anom.repo_name}</strong> shows a {anom.failure_rate}% failure rate across {anom.total_runs} runs.
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Health Gauge & Metric Cards Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 3fr', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
          {/* Health Score Circular Gauge */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-5)' }}>
            <h3 style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 12 }}>System Health Score</h3>
            <HealthGauge score={healthScore} size={120} />
          </div>

          {/* Metric Cards */}
          <div className="grid grid-3" style={{ gap: 'var(--space-4)', gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <MetricCard
              label="Total Runs"
              value={totalRuns}
              loading={loadingMetrics}
              icon={
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              }
            />
            <MetricCard
              label="Success Rate"
              value={successRate}
              loading={loadingMetrics}
              variant="success"
              icon={
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
              }
            />
            <MetricCard
              label="Mean Time to Repair (MTTR)"
              value={mttrMinutes}
              loading={loadingMetrics}
              variant="warning"
              icon={
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              }
            />
          </div>
        </div>

        {/* Heatmap Section */}
        <div className="card" style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-6)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
            <div>
              <h2 className="section-title" style={{ margin: 0 }}>Failure Heatmap</h2>
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Identifies hourly distribution of build failures across the last 7 days.
              </p>
            </div>
          </div>
          {loadingHeatmap ? (
            <div className="skeleton" style={{ height: 160, width: '100%' }} />
          ) : heatmapResponse?.heatmap && Object.keys(heatmapResponse.heatmap).length > 0 ? (
            <Heatmap data={heatmapResponse.heatmap} />
          ) : (
            <EmptyState
              title="No Heatmap Data Available"
              description="No failures recorded in the tracking period."
            />
          )}
        </div>

        {/* Recent Runs List */}
        <div className="card" style={{ padding: 'var(--space-6)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
            <div>
              <h2 className="section-title" style={{ margin: 0 }}>Recent Pipeline Runs</h2>
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Real-time workflow execution log. Click a run to view detailed logs and AI analysis.
              </p>
            </div>
            <Link href="/runs" className="btn btn-ghost btn-sm">
              View All Runs
            </Link>
          </div>

          {loadingRuns ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="skeleton" style={{ height: 48, width: '100%' }} />
              <div className="skeleton" style={{ height: 48, width: '100%' }} />
              <div className="skeleton" style={{ height: 48, width: '100%' }} />
            </div>
          ) : runsResponse?.runs && runsResponse.runs.length > 0 ? (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Workflow & Branch</th>
                    <th>Commit</th>
                    <th>Trigger</th>
                    <th>Status</th>
                    <th>Started</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {runsResponse.runs.map(run => (
                    <tr key={run.id}>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
                          {run.name} #{run.github_run_number}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span>{run.repository?.full_name || 'unknown/repo'}</span>
                          <span style={{ color: 'var(--color-border-bright)' }}>•</span>
                          <span className="font-mono text-xs">{run.head_branch}</span>
                        </div>
                      </td>
                      <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)' }}>
                          {run.head_commit?.message || 'No commit message'}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                          by {run.head_commit?.author?.name || 'unknown'}
                        </div>
                      </td>
                      <td>
                        <span style={{ textTransform: 'capitalize', fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                          {run.event}
                        </span>
                      </td>
                      <td>
                        <StatusBadge conclusion={run.conclusion} status={run.status} />
                      </td>
                      <td style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                        {new Date(run.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link href={`/runs/${run.id}`} className="btn btn-outline btn-sm">
                          Details
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No Runs Found"
              description="Connect a GitHub repository to trigger workflow runs."
            />
          )}
        </div>
      </main>
    </>
  )
}
