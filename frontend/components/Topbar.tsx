'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { getUser } from '@/lib/utils'

export default function Topbar({ title }: { title?: string }) {
  const [user, setUser] = useState<ReturnType<typeof getUser>>(null)
  const [search, setSearch] = useState('')

  useEffect(() => { setUser(getUser()) }, [])

  return (
    <header className="topbar" id="topbar">
      {/* Page title */}
      <div style={{ flex: 1 }}>
        {title && (
          <h1 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
            {title}
          </h1>
        )}
      </div>

      {/* Search */}
      <div className="search-wrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          id="topbar-search"
          className="search-input"
          type="search"
          placeholder="Search runs, repos, commits…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          aria-label="Global search"
        />
      </div>

      {/* Notification bell */}
      <Link href="/notifications">
        <button className="btn btn-ghost btn-icon" id="btn-notifications" aria-label="Notifications" style={{ position: 'relative' }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span style={{
            position: 'absolute', top: 4, right: 4,
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--color-error)',
            border: '2px solid var(--color-bg-base)',
          }} />
        </button>
      </Link>

      {/* User avatar */}
      {user && (
        <Link href="/settings">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} id="topbar-user">
            <img
              src={user.avatar_url || `https://github.com/${user.github_login}.png`}
              alt={user.name}
              width={30} height={30}
              style={{ borderRadius: '50%', border: '2px solid var(--color-border)' }}
            />
            <div style={{ lineHeight: 1.3 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-primary)' }}>{user.name}</div>
              <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                <span className="badge badge-muted" style={{ textTransform: 'capitalize', fontSize: 9 }}>{user.role}</span>
              </div>
            </div>
          </div>
        </Link>
      )}
    </header>
  )
}
