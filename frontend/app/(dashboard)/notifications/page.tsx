'use client'

import { useEffect, useState } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { EmptyState } from '@/components/ui'
import Link from 'next/link'

interface Notification {
  id: string
  type: string
  repo_name: string
  read: boolean
  created_at: string
  data: {
    run_id?: string
    run_number?: number
    branch?: string
    actor?: string
    executive_summary?: string
    severity?: string
    root_cause_category?: string
  }
}

interface NotificationsResponse {
  notifications: Notification[]
  total: number
}

export default function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [page, setPage] = useState(1)

  const buildQuery = () => {
    const params = new URLSearchParams()
    if (unreadOnly) params.append('unread_only', 'true')
    params.append('page', String(page))
    params.append('per_page', '15')
    return `/notifications?${params.toString()}`
  }

  const { data, loading, error } = useApi<NotificationsResponse>(buildQuery(), [unreadOnly, page])

  async function markAsRead(id: string) {
    try {
      const res = await apiFetch(`/notifications/${id}/read`, { method: 'POST' })
      if (res.ok) {
        // Optimistically update
        window.location.reload()
      }
    } catch (e) {
      console.error(e)
    }
  }

  async function markAllAsRead() {
    try {
      const res = await apiFetch('/notifications/read-all', { method: 'POST' })
      if (res.ok) {
        window.location.reload()
      }
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <>
      <Topbar title="Alerts & Notifications" />
      <main className="page-content">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          <div style={{ display: 'flex', gap: 12 }}>
            <button
              className={`btn btn-sm ${!unreadOnly ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => {
                setUnreadOnly(false)
                setPage(1)
              }}
            >
              All Alerts
            </button>
            <button
              className={`btn btn-sm ${unreadOnly ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => {
                setUnreadOnly(true)
                setPage(1)
              }}
            >
              Unread Only
            </button>
          </div>

          {data && data.notifications.some(n => !n.read) && (
            <button className="btn btn-outline btn-sm" onClick={markAllAsRead}>
              Mark All Read
            </button>
          )}
        </div>

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="skeleton" style={{ height: 72 }} />
            <div className="skeleton" style={{ height: 72 }} />
            <div className="skeleton" style={{ height: 72 }} />
          </div>
        ) : data && data.notifications.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {data.notifications.map(notif => {
              const isFailure = notif.type === 'workflow_failure'
              const isTriggered = notif.type === 'workflow_triggered'
              return (
                <div
                  key={notif.id}
                  style={{
                    padding: 'var(--space-4) var(--space-5)',
                    background: notif.read ? 'var(--color-bg-surface)' : 'rgba(139, 92, 246, 0.04)',
                    border: '1px solid',
                    borderColor: notif.read ? 'var(--color-border)' : 'rgba(139, 92, 246, 0.15)',
                    borderRadius: 8,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 16,
                    transition: 'all 0.2s ease',
                    position: 'relative'
                  }}
                >
                  {/* Indicator dot */}
                  {!notif.read && (
                    <div style={{
                      position: 'absolute', left: 4, top: '50%', transform: 'translateY(-50%)',
                      width: 6, height: 6, borderRadius: '50%', background: 'var(--color-accent)'
                    }} />
                  )}

                  {/* Icon */}
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: isFailure ? 'var(--color-error-muted)' : isTriggered ? 'var(--color-warning-muted)' : 'var(--color-ai-muted)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                  }}>
                    {isFailure ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-error)" strokeWidth="2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    ) : isTriggered ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning)" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-ai-start)" strokeWidth="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
                    )}
                  </div>

                  {/* Main Details */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                        {isFailure ? 'Pipeline Failed' : isTriggered ? 'Pipeline Triggered' : 'AI Analysis Complete'}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                        • {notif.repo_name}
                      </span>
                    </div>

                    <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {isFailure
                        ? `Run #${notif.data.run_number} failed on branch ${notif.data.branch} by ${notif.data.actor}`
                        : isTriggered
                        ? `Run #${notif.data.run_number} started on branch ${notif.data.branch} by ${notif.data.actor}`
                        : notif.data.executive_summary || `Analysis completed for run #${notif.data.run_number}`}
                    </p>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                      {new Date(notif.created_at).toLocaleDateString()}
                    </span>

                    {notif.data.run_id && (
                      <Link href={`/runs/${notif.data.run_id}`} className="btn btn-outline btn-sm">
                        View
                      </Link>
                    )}

                    {!notif.read && (
                      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => markAsRead(notif.id)} title="Mark as read">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <EmptyState
            title="No Alerts Found"
            description="No system alerts or notifications registered."
          />
        )}
      </main>
    </>
  )
}
