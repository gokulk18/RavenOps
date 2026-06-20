'use client'

import { useEffect } from 'react'

export default function AuthCallbackPage() {
  useEffect(() => {
    // Forward query parameters (code, state) to the login page
    const params = window.location.search
    window.location.href = `/login${params}`
  }, [])

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--color-bg-base)' }}>
      <div style={{ width: 32, height: 32, borderRadius: '50%', border: '3px solid var(--color-border)', borderTopColor: 'var(--color-accent)', animation: 'spin 1s linear infinite' }} />
    </div>
  )
}
