'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { getUser } from '@/lib/utils'
import { useEffect, useState } from 'react'

const NAV = [
  { href: '/dashboard',   label: 'Overview',     icon: 'grid' },
  { href: '/repositories', label: 'Repositories', icon: 'git-branch' },
  { href: '/runs',         label: 'Runs',          icon: 'play-circle' },
  { href: '/ai-insights',  label: 'AI Insights',   icon: 'sparkles', ai: true },
  { href: '/analytics',    label: 'Analytics',     icon: 'bar-chart-2' },
  { href: '/notifications',label: 'Notifications', icon: 'bell', badge: 3 },
  { href: '/settings',     label: 'Settings',      icon: 'settings' },
]

function Icon({ name, size = 16 }: { name: string; size?: number }) {
  const icons: Record<string, React.ReactNode> = {
    grid: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
    'git-branch': <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>,
    'play-circle': <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>,
    sparkles: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>,
    'bar-chart-2': <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,
    bell: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
    settings: <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>,
    raven: <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"><path d="M21 3L14.5 8.5 12 6l-9 9 2 2 7-7 2.5 2.5L8 19l2 2 8-8-2.5-2.5L21 3z"/></svg>,
    'log-out': <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>,
  }
  return <>{icons[name] || null}</>
}

export default function Sidebar() {
  const pathname = usePathname()
  const [user, setUser] = useState<ReturnType<typeof getUser>>(null)

  useEffect(() => { setUser(getUser()) }, [])

  function handleLogout() {
    const rt = localStorage.getItem('refresh_token')
    if (rt) {
      fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/logout`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      }).catch(() => {})
    }
    localStorage.clear()
    window.location.href = '/login'
  }

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          <Icon name="raven" size={18} />
        </div>
        <div>
          <div className="sidebar-logo-text">RavenOps</div>
        </div>
        <span className="sidebar-logo-badge">v1</span>
      </div>

      {/* Main nav */}
      <div style={{ padding: '8px 0', flex: 1 }}>
        <div className="sidebar-section-label">Navigation</div>
        {NAV.map(item => {
          const active = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link key={item.href} href={item.href}>
              <div className={`nav-item${active ? ' active' : ''}`} id={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}>
                <span style={item.ai ? { background: 'linear-gradient(135deg, var(--color-ai-start), var(--color-ai-end))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', display: 'flex' } : {}}>
                  <Icon name={item.icon} size={16} />
                </span>
                <span>{item.label}</span>
                {item.badge && !active ? <span className="nav-badge">{item.badge}</span> : null}
              </div>
            </Link>
          )
        })}
      </div>

      {/* User footer */}
      <div className="sidebar-footer">
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img
              src={user.avatar_url || `https://github.com/${user.github_login}.png`}
              alt={user.name}
              width={32} height={32}
              style={{ borderRadius: '50%', border: '2px solid var(--color-border)' }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.name}</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>@{user.github_login}</div>
            </div>
            <button className="btn btn-ghost btn-icon" onClick={handleLogout} title="Log out" id="btn-logout">
              <Icon name="log-out" size={14} />
            </button>
          </div>
        ) : (
          <Link href="/login">
            <div className="btn btn-primary btn-sm" style={{ width: '100%', justifyContent: 'center' }}>Sign In</div>
          </Link>
        )}
      </div>
    </aside>
  )
}
