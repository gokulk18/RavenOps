'use client'

import { useEffect, useState } from 'react'
import Topbar from '@/components/Topbar'
import { useApi } from '@/lib/utils'
import { MetricCard, EmptyState, SeverityBadge, ConfidenceBar } from '@/components/ui'
import Link from 'next/link'

interface AIAnalysisListItem {
  id: string
  run_id: string
  repo_id: string
  model_used: string
  analyzed_at: string
  duration_ms: number
  executive_summary: string
  root_cause: {
    primary: string
    category: string
    confidence: number
  }
  severity: {
    level: string
  }
  is_flaky: boolean
}

interface RecentAnalysisResponse {
  analyses: AIAnalysisListItem[]
}

export default function AIInsightsPage() {
  const { data, loading, error } = useApi<RecentAnalysisResponse>('/analysis/recent?limit=20')

  // Calculate statistics from the list
  const totalCount = data?.analyses?.length || 0
  const avgConfidence = totalCount > 0
    ? Math.round((data!.analyses.reduce((acc, curr) => acc + (curr.root_cause?.confidence || 0), 0) / totalCount) * 100)
    : 0

  const flakyCount = data?.analyses?.filter(a => a.is_flaky).length || 0
  const flakyRate = totalCount > 0 ? `${Math.round((flakyCount / totalCount) * 100)}%` : '0%'

  // Group by category
  const categories: Record<string, number> = {}
  data?.analyses?.forEach(a => {
    const cat = a.root_cause?.category || 'unknown'
    categories[cat] = (categories[cat] || 0) + 1
  })

  const topCategoryRaw = Object.keys(categories).length > 0
    ? Object.entries(categories).sort((a, b) => b[1] - a[1])[0][0]
    : 'None'
  const topCategory = topCategoryRaw.charAt(0).toUpperCase() + topCategoryRaw.slice(1)

  return (
    <>
      <Topbar title="AI Observability & Insights" />
      <main className="page-content">
        {/* KPI Row */}
        <div className="grid grid-4" style={{ marginBottom: 'var(--space-6)' }}>
          <MetricCard
            label="Total AI RCA Reports"
            value={totalCount}
            loading={loading}
            variant="ai"
          />
          <MetricCard
            label="Avg RCA Confidence"
            value={totalCount > 0 ? `${avgConfidence}%` : '—'}
            loading={loading}
            variant="success"
          />
          <MetricCard
            label="Top Root Category"
            value={topCategory}
            loading={loading}
          />
          <MetricCard
            label="Flakiness Rate"
            value={flakyRate}
            loading={loading}
            variant="warning"
          />
        </div>

        {/* RCA Reports List */}
        <div className="card" style={{ padding: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-4) 0' }}>
            Recent Root Cause Analysis Reports
          </h3>

          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="skeleton" style={{ height: 64 }} />
              <div className="skeleton" style={{ height: 64 }} />
              <div className="skeleton" style={{ height: 64 }} />
            </div>
          ) : data && data.analyses.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {data.analyses.map(analysis => (
                <div
                  key={analysis.id}
                  style={{
                    padding: 'var(--space-5)',
                    background: 'var(--color-bg-surface)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <SeverityBadge level={analysis.severity?.level || 'medium'} />
                      <span className="font-mono" style={{ fontSize: 11, background: 'var(--color-accent-muted)', color: 'var(--color-accent)', padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>
                        {analysis.root_cause?.category || 'unknown'}
                      </span>
                      {analysis.is_flaky && (
                        <span className="badge badge-warning" style={{ fontSize: 10 }}>
                          Flaky Run
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>
                      Analyzed {new Date(analysis.analyzed_at).toLocaleString()}
                    </span>
                  </div>

                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', fontWeight: 600 }}>
                    {analysis.root_cause?.primary || 'No cause classified'}
                  </div>

                  <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', margin: 0, lineHeight: 1.4 }}>
                    {analysis.executive_summary}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-3)', marginTop: 4 }}>
                    <div style={{ width: 180 }}>
                      <ConfidenceBar value={analysis.root_cause?.confidence || 0} />
                    </div>
                    <Link href={`/runs/${analysis.run_id}`} className="btn btn-outline btn-sm">
                      Inspect Build & Logs →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No AI Analyses Found"
              description="RCA reports are generated automatically when a connected repository build fails."
            />
          )}
        </div>
      </main>
    </>
  )
}
