'use client'

import { useEffect, useState } from 'react'
import Topbar from '@/components/Topbar'
import { getUser, clearAuth } from '@/lib/utils'
import { MetricCard } from '@/components/ui'

export default function SettingsPage() {
  const [user, setUser] = useState<ReturnType<typeof getUser>>(null)
  const [smtpServer, setSmtpServer] = useState('mailhog:1025')
  const [emailAlerts, setEmailAlerts] = useState('team@ravenops.local')
  const [slackWebhook, setSlackWebhook] = useState('https://hooks.slack.com/services/...')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setUser(getUser())
  }, [])

  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setTimeout(() => {
      setSaving(false)
      alert('Integration settings saved successfully!')
    }, 1000)
  }

  function handleLogout() {
    clearAuth()
    window.location.href = '/login'
  }

  return (
    <>
      <Topbar title="Settings & Integrations" />
      <main className="page-content">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 'var(--space-6)' }}>
          {/* Left panel: Profile Card */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
            <div className="card" style={{ padding: 'var(--space-6)', textAlign: 'center' }}>
              {user ? (
                <>
                  <img
                    src={user.avatar_url || `https://github.com/${user.github_login}.png`}
                    alt={user.name}
                    width={96}
                    height={96}
                    style={{ borderRadius: '50%', margin: '0 auto var(--space-4)', border: '3px solid var(--color-border)' }}
                  />
                  <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 4px 0' }}>{user.name}</h3>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', marginBottom: 'var(--space-4)' }}>@{user.github_login}</div>
                  <div style={{ display: 'inline-block', padding: '4px 12px', borderRadius: 12, background: 'var(--color-accent-muted)', color: 'var(--color-accent)', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', marginBottom: 'var(--space-6)' }}>
                    Role: {user.role}
                  </div>

                  <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-4)' }}>
                    <button className="btn btn-outline" style={{ width: '100%', borderColor: 'var(--color-error)', color: 'var(--color-error)', justifyContent: 'center' }} onClick={handleLogout}>
                      Sign Out
                    </button>
                  </div>
                </>
              ) : (
                <div className="skeleton" style={{ height: 200 }} />
              )}
            </div>

            {/* Auth Session Info */}
            <div className="card" style={{ padding: 'var(--space-6)' }}>
              <h4 style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', margin: '0 0 12px 0' }}>Session Info</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Environment:</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>development</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>Auth Provider:</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>GitHub OAuth</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>API Version:</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>v2.0.0</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right panel: Global Integrations */}
          <div className="card" style={{ padding: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 var(--space-5) 0' }}>
              System Integrations
            </h3>

            <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              {/* SMTP Settings */}
              <div>
                <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 12px 0', borderBottom: '1px solid var(--color-border)', paddingBottom: 6 }}>
                  Email Notifications (SMTP)
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 8 }}>SMTP Host & Port</label>
                    <input
                      type="text"
                      value={smtpServer}
                      onChange={e => setSmtpServer(e.target.value)}
                      style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 8 }}>Alert Destination Email</label>
                    <input
                      type="email"
                      value={emailAlerts}
                      onChange={e => setEmailAlerts(e.target.value)}
                      style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
                    />
                  </div>
                </div>
              </div>

              {/* Slack Integrations */}
              <div>
                <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 12px 0', borderBottom: '1px solid var(--color-border)', paddingBottom: 6 }}>
                  Slack Channel Integration
                </h4>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 8 }}>Incoming Webhook URL</label>
                  <input
                    type="text"
                    value={slackWebhook}
                    onChange={e => setSlackWebhook(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}
                  />
                  <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 6 }}>
                    Workflow failure summaries and AI Root Cause summaries will be posted directly to this Slack workspace.
                  </p>
                </div>
              </div>

              {/* MS Teams */}
              <div>
                <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-text-primary)', margin: '0 0 12px 0', borderBottom: '1px solid var(--color-border)', paddingBottom: 6 }}>
                  Microsoft Teams Integration
                </h4>
                <div>
                  <label style={{ display: 'block', fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 8 }}>Incoming Webhook URL</label>
                  <input
                    type="text"
                    disabled
                    placeholder="https://outlook.office.com/webhook/..."
                    style={{ width: '100%', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--color-border)', background: 'var(--color-bg-base)', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)', cursor: 'not-allowed' }}
                  />
                  <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginTop: 6 }}>
                    Microsoft Teams connector is disabled in development mode.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </main>
    </>
  )
}
