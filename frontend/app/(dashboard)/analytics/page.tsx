'use client'

import { useState } from 'react'
import Topbar from '@/components/Topbar'
import { useApi } from '@/lib/utils'
import { MetricCard, EmptyState, SeverityBadge } from '@/components/ui'

interface AnalyticsOverview {
  total_repos: number
  total_runs_30d: number
  success_rate_30d: number
  failure_rate_30d: number
  in_progress: number
  runs_24h: number
  failed_24h: number
  avg_duration_seconds: number
}

interface ErrorCategory {
  category: string
  count: number
  percentage: number
}

interface ErrorsResponse {
  distribution: ErrorCategory[]
  total_errors: number
}

interface Anomaly {
  repo_id: string
  repo_name: string
  failure_rate: number
  total_runs: number
  failed_runs: number
  type: string
  severity: string
}

interface AnomaliesResponse {
  anomalies: Anomaly[]
}

interface TopRepo {
  repo_id: string | null
  repo_name: string
  failure_count: number
}

interface TopReposResponse {
  top_failing_repos: TopRepo[]
}

interface MttrDay {
  date: string
  avg_mttr_seconds: number
  sample_size: number
}

interface MttrResponse {
  mttr_by_day: MttrDay[]
}

export default function AnalyticsPage() {
  const { data: overview, loading: loadingOverview } = useApi<AnalyticsOverview>('/analytics/overview')
  const { data: errors, loading: loadingErrors } = useApi<ErrorsResponse>('/analytics/errors/distribution')
  const { data: anomalies, loading: loadingAnomalies } = useApi<AnomaliesResponse>('/analytics/anomalies')
  const { data: topRepos, loading: loadingTopRepos } = useApi<TopReposResponse>('/analytics/failures/top')
  const { data: mttrData, loading: loadingMttr } = useApi<MttrResponse>('/analytics/mttr')

  return (
    <>
      <Topbar title="DevOps Analytics Dashboard" />
      <main className="page-content">
        {/* Metric Cards */}
        <div className="grid grid-4" style={{ marginBottom: 'var(--space-6)' }}>
          <MetricCard
            label="Total Runs (30 Days)"
            value={overview ? overview.total_runs_30d.toLocaleString() : '—'}
            loading={loadingOverview}
          />
          <MetricCard
            label="Failure Rate (30 Days)"
            value={overview ? `${overview.failure_rate_30d}%` : '—'}
            loading={loadingOverview}
            variant={overview && overview.failure_rate_30d > 25 ? 'error' : 'default'}
          />
          <MetricCard
            label="Avg Duration"
            value={overview ? `${Math.round(overview.avg_duration_seconds / 60)}m ${overview.avg_duration_seconds % 60}s` : '—'}
            loading={loadingOverview}
          />
          <MetricCard
            label="Active Anomalies"
            value={anomalies ? anomalies.anomalies.length : 0}
            loading={loadingAnomalies}
            variant={anomalies && anomalies.anomalies.length > 0 ? 'warning' : 'success'}
          />
        </div>

        {/* Anomaly Detections Alert Section */}
        {anomalies && anomalies.anomalies.length > 0 && (
          <div className="card animate-fade-in" style={{ padding: 'var(--space-5) var(--space-6)', marginBottom: 'var(--space-6)', borderColor: 'var(--color-warning)', background: 'var(--color-warning-muted)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-warning)', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              Anomaly Alerts Detected
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {anomalies.anomalies.map((anom, idx) => (
                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-primary)' }}>
                    Repository <strong>{anom.repo_name}</strong> is experiencing an abnormally high failure rate of <strong>{anom.failure_rate}%</strong> ({anom.failed_runs} of {anom.total_runs} runs).
                  </span>
                  <SeverityBadge level={anom.severity} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Analytics Breakdown Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', marginBottom: 'var(--space-6)' }}>
          {/* Error Classification Distribution */}
          <div className="card" style={{ padding: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Error Category Distribution
            </h3>

            {loadingErrors ? (
              <div className="skeleton" style={{ height: 160 }} />
            ) : errors && errors.distribution.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {errors.distribution.map((cat, idx) => (
                  <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                      <span style={{ textTransform: 'capitalize', color: 'var(--color-text-primary)' }}>{cat.category}</span>
                      <span style={{ color: 'var(--color-text-secondary)' }}>{cat.count} ({cat.percentage}%)</span>
                    </div>
                    <div style={{ height: 8, background: 'var(--color-bg-base)', borderRadius: 4, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%',
                        width: `${cat.percentage}%`,
                        background: 'linear-gradient(90deg, var(--color-ai-start), var(--color-accent))',
                        borderRadius: 4
                      }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No parsed error distribution data found" />
            )}
          </div>

          {/* Top Failing Repositories */}
          <div className="card" style={{ padding: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
              Top Failing Repositories (Last 7 Days)
            </h3>

            {loadingTopRepos ? (
              <div className="skeleton" style={{ height: 160 }} />
            ) : topRepos && topRepos.top_failing_repos.length > 0 ? (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Repository</th>
                      <th style={{ textAlign: 'right' }}>Failures Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topRepos.top_failing_repos.map((repo, idx) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 700, color: idx === 0 ? 'var(--color-error)' : 'var(--color-text-secondary)' }}>#{idx + 1}</td>
                        <td style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{repo.repo_name}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--color-error)' }}>{repo.failure_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No failures detected this week" />
            )}
          </div>
        </div>

        {/* MTTR Breakdown panel */}
        <div className="card" style={{ padding: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
            Mean Time to Recovery (MTTR) Trend
          </h3>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginTop: -8, marginBottom: 20 }}>
            Tracks average duration from a build failure to the next successful run on the same branch.
          </p>

          {loadingMttr ? (
            <div className="skeleton" style={{ height: 140 }} />
          ) : mttrData && mttrData.mttr_by_day.length > 0 ? (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Average MTTR</th>
                    <th>Resolved Issues</th>
                  </tr>
                </thead>
                <tbody>
                  {mttrData.mttr_by_day.map((day, idx) => {
                    const mttrFormatted = day.avg_mttr_seconds < 60
                      ? `${day.avg_mttr_seconds}s`
                      : `${Math.round(day.avg_mttr_seconds / 60)}m`

                    return (
                      <tr key={idx}>
                        <td>{day.date}</td>
                        <td style={{ fontWeight: 600, color: day.avg_mttr_seconds > 1800 ? 'var(--color-error)' : 'var(--color-success)' }}>
                          {mttrFormatted}
                        </td>
                        <td>{day.sample_size} recoveries</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No MTTR metrics tracked yet"
              description="MTTR is computed when a branch succeeds after a previous failure."
            />
          )}
        </div>
      </main>
    </>
  )
}
