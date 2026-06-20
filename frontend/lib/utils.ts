'use client'

import { useEffect, useRef, useState } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Fetch helper ─────────────────────────────────────────────
export async function apiFetch(path: string, opts?: RequestInit) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(opts?.headers as Record<string, string> || {}),
  }
  const res = await fetch(`${API}${path}`, { ...opts, headers })
  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    throw new Error('Unauthorized')
  }
  return res
}

// ── Auth store (simple, no deps needed) ─────────────────────
export interface AuthUser {
  id: string
  github_login: string
  name: string
  email?: string
  avatar_url?: string
  role: string
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  const u = localStorage.getItem('user')
  return u ? JSON.parse(u) : null
}

export function setAuth(token: string, refresh: string, user: AuthUser) {
  localStorage.setItem('access_token', token)
  localStorage.setItem('refresh_token', refresh)
  localStorage.setItem('user', JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
}

// ── Custom hooks ──────────────────────────────────────────────
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(!!path)
  const [error, setError] = useState<string | null>(null)
  const [refreshIndex, setRefreshIndex] = useState(0)

  const mutate = () => setRefreshIndex(prev => prev + 1)

  useEffect(() => {
    if (!path) return
    setLoading(true)
    setError(null)
    apiFetch(path)
      .then(r => r.json())
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, refreshIndex, ...deps])

  return { data, loading, error, mutate }
}

// ── Format helpers ────────────────────────────────────────────
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function formatRelative(date: string | Date | null | undefined): string {
  if (!date) return '—'
  const d = new Date(date)
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60_000)  return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return '—'
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(date))
}

// ── Status helpers ────────────────────────────────────────────
export function conclusionBadgeClass(conclusion: string | null): string {
  switch (conclusion) {
    case 'success':   return 'badge badge-success'
    case 'failure':   return 'badge badge-error'
    case 'cancelled': return 'badge badge-muted'
    case 'skipped':   return 'badge badge-muted'
    case 'timed_out': return 'badge badge-warning'
    default:          return 'badge badge-info'
  }
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case 'completed':   return 'badge badge-success'
    case 'in_progress': return 'badge badge-warning'
    case 'queued':      return 'badge badge-muted'
    default:            return 'badge badge-muted'
  }
}

export function severityClass(level: string): string {
  switch (level) {
    case 'critical': return 'badge badge-critical'
    case 'high':     return 'badge badge-error'
    case 'medium':   return 'badge badge-warning'
    case 'low':      return 'badge badge-success'
    default:         return 'badge badge-muted'
  }
}

export function healthColor(score: number): string {
  if (score >= 80) return 'var(--color-success)'
  if (score >= 60) return 'var(--color-warning)'
  return 'var(--color-error)'
}
