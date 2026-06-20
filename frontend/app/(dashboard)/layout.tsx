'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'
import { getUser } from '@/lib/utils'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [authorized, setAuthorized] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const user = getUser()
    if (!user) {
      window.location.href = '/login'
    } else {
      setAuthorized(true)
      setLoading(false)
    }
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', height: '100vh', width: '100vw', alignItems: 'center', justifyContent: 'center', background: '#0A0A0B', color: '#FAFAFA' }}>
        <div className="skeleton" style={{ height: 48, width: 48, borderRadius: '50%' }} />
      </div>
    )
  }

  if (!authorized) return null

  return (
    <div className="layout-root">
      <Sidebar />
      <div className="main-area">
        {children}
      </div>
    </div>
  )
}
