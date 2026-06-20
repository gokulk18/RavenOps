'use client'

import { useEffect, useState } from 'react'
import { apiFetch, setAuth } from '@/lib/utils'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    // Already logged in?
    const token = localStorage.getItem('access_token')
    if (token) {
      window.location.href = '/dashboard'
    } else {
      setChecking(false)
    }

    // Handle OAuth callback
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    if (code) {
      handleCallback(code, state || '')
    }
  }, [])

  async function handleCallback(code: string, state: string) {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API}/auth/github/oauth/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, state }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Authentication failed')
      setAuth(data.access_token, data.refresh_token, data.user)
      window.location.href = '/dashboard'
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Login failed')
      setLoading(false)
      setChecking(false)
    }
  }

  async function handleLogin() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API}/auth/github/oauth/authorize`)
      const data = await res.json()
      window.location.href = data.authorization_url
    } catch {
      setError('Could not connect to auth service. Make sure the backend is running.')
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--color-bg-base)' }}>
        <div style={{ width: 32, height: 32, borderRadius: '50%', border: '3px solid var(--color-border)', borderTopColor: 'var(--color-accent)', animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none',
      }}>
        <div style={{ position: 'absolute', top: '20%', left: '50%', transform: 'translateX(-50%)', width: 600, height: 400, background: 'radial-gradient(ellipse, rgba(34,197,94,0.07) 0%, transparent 70%)', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', bottom: '20%', right: '20%', width: 400, height: 300, background: 'radial-gradient(ellipse, rgba(139,92,246,0.06) 0%, transparent 70%)', pointerEvents: 'none' }} />
      </div>

      <div className="animate-fade-in" style={{ width: '100%', maxWidth: 420, padding: 24 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 18,
            background: 'linear-gradient(135deg, var(--color-accent), var(--color-accent-dim))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px', boxShadow: '0 0 32px rgba(34,197,94,0.3)',
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="white"><path d="M21 3L14.5 8.5 12 6l-9 9 2 2 7-7 2.5 2.5L8 19l2 2 8-8-2.5-2.5L21 3z"/></svg>
          </div>
          <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.025em', marginBottom: 8 }}>Welcome back</h1>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: 14 }}>Sign in to your RavenOps workspace</p>
        </div>

        {/* Card */}
        <div className="card" style={{ padding: 32, borderColor: 'var(--color-border-bright)' }}>
          {error && (
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 24,
              background: 'var(--color-error-muted)', border: '1px solid rgba(239,68,68,0.3)',
              color: 'var(--color-error)', fontSize: 13,
            }}>
              {error}
            </div>
          )}

          <button
            id="btn-github-login"
            className="btn btn-primary btn-lg"
            onClick={handleLogin}
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', gap: 12, fontSize: 15 }}
          >
            {loading ? (
              <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid rgba(0,0,0,0.3)', borderTopColor: '#000', animation: 'spin 1s linear infinite' }} />
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
            )}
            {loading ? 'Authenticating…' : 'Continue with GitHub'}
          </button>

          <div style={{ marginTop: 24, padding: '16px', borderRadius: 10, background: 'var(--color-bg-elevated)', border: '1px solid var(--color-border)' }}>
            <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', lineHeight: 1.6 }}>
              <strong style={{ color: 'var(--color-text-secondary)' }}>What we request:</strong> Read access to repos and workflows. We never store your GitHub credentials.
            </div>
          </div>
        </div>

        <p style={{ textAlign: 'center', marginTop: 24, fontSize: 13, color: 'var(--color-text-tertiary)' }}>
          Don&apos;t have an account?{' '}
          <a href="#" style={{ color: 'var(--color-accent)' }}>Learn more</a>
        </p>
      </div>
    </div>
  )
}
