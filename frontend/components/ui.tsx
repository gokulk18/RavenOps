'use client'

import { healthColor, conclusionBadgeClass, statusBadgeClass } from '@/lib/utils'

// ── MetricCard ────────────────────────────────────────────────
interface MetricCardProps {
  label: string
  value: string | number
  delta?: { value: string; direction: 'up' | 'down' | 'flat' }
  variant?: 'default' | 'success' | 'error' | 'warning' | 'ai'
  icon?: React.ReactNode
  loading?: boolean
}

export function MetricCard({ label, value, delta, variant = 'default', icon, loading }: MetricCardProps) {
  if (loading) {
    return (
      <div className="metric-card">
        <div className="skeleton" style={{ height: 12, width: '60%', marginBottom: 8 }} />
        <div className="skeleton" style={{ height: 36, width: '80%', marginBottom: 8 }} />
        <div className="skeleton" style={{ height: 10, width: '40%' }} />
      </div>
    )
  }
  return (
    <div className="metric-card animate-fade-in">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="metric-label">{label}</span>
        {icon && <span style={{ color: 'var(--color-text-tertiary)' }}>{icon}</span>}
      </div>
      <div className={`metric-value ${variant !== 'default' ? variant : ''}`}>{value}</div>
      {delta && (
        <div className={`metric-delta ${delta.direction}`}>
          {delta.direction === 'up' ? '↑' : delta.direction === 'down' ? '↓' : '→'}
          {delta.value}
        </div>
      )}
    </div>
  )
}

// ── StatusBadge ───────────────────────────────────────────────
export function StatusBadge({ conclusion, status }: { conclusion?: string | null; status?: string }) {
  if (conclusion) {
    return (
      <span className={conclusionBadgeClass(conclusion)}>
        <span className="badge-dot" />
        {conclusion.replace(/_/g, ' ')}
      </span>
    )
  }
  if (status) {
    return (
      <span className={statusBadgeClass(status)}>
        <span className="badge-dot" style={{ animation: status === 'in_progress' ? 'pulse 1.5s infinite' : undefined }} />
        {status.replace(/_/g, ' ')}
      </span>
    )
  }
  return <span className="badge badge-muted">—</span>
}

// ── SeverityBadge ─────────────────────────────────────────────
export function SeverityBadge({ level }: { level: string }) {
  const classes: Record<string, string> = {
    critical: 'badge badge-critical',
    high:     'badge badge-error',
    medium:   'badge badge-warning',
    low:      'badge badge-success',
  }
  return <span className={classes[level] || 'badge badge-muted'}>{level}</span>
}

// ── HealthGauge ───────────────────────────────────────────────
export function HealthGauge({ score, size = 120 }: { score: number; size?: number }) {
  const radius = (size - 20) / 2
  const circumference = 2 * Math.PI * radius
  const dash = (score / 100) * circumference
  const color = healthColor(score)

  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', position: 'absolute' }}>
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="var(--color-bg-muted)" strokeWidth={10} />
        <circle
          cx={size/2} cy={size/2} r={radius} fill="none"
          stroke={color} strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          className="health-gauge-ring"
          style={{ transition: 'stroke-dasharray 1s ease' }}
        />
      </svg>
      <div style={{ textAlign: 'center', zIndex: 1 }}>
        <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{score}</div>
        <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', marginTop: 2 }}>Health</div>
      </div>
    </div>
  )
}

// ── ConfidenceBar ─────────────────────────────────────────────
export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div className="confidence-bar-track" style={{ flex: 1 }}>
        <div className="confidence-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-ai-end)', minWidth: 32, fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
    </div>
  )
}

// ── AICard (purple gradient border) ───────────────────────────
export function AICard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`card-ai ${className}`}>
      <div style={{ padding: 'var(--space-6)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--space-4)' }}>
          <div style={{
            width: 24, height: 24, borderRadius: 6,
            background: 'linear-gradient(135deg, var(--color-ai-start), var(--color-ai-end))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
            </svg>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', background: 'linear-gradient(135deg, var(--color-ai-start), var(--color-ai-end))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            AI Analysis
          </span>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Skeleton ─────────────────────────────────────────────────
export function Skeleton({ width = '100%', height = 16 }: { width?: string | number; height?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 4 }} />
}

// ── Empty State ───────────────────────────────────────────────
export function EmptyState({ icon, title, description, action }: {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <div className="empty-state-title">{title}</div>
      {description && <div className="empty-state-desc">{description}</div>}
      {action}
    </div>
  )
}

// ── Heatmap ───────────────────────────────────────────────────
export function Heatmap({ data }: { data: Record<string, Record<string, number>> }) {
  const days = Object.keys(data)
  const hours = Array.from({ length: 24 }, (_, i) => i)
  const maxVal = Math.max(...days.flatMap(d => hours.map(h => data[d]?.[String(h)] || 0)), 1)

  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: `40px repeat(24, 1fr)`, gap: 3, minWidth: 600 }}>
        {/* Hour labels */}
        <div />
        {hours.map(h => (
          <div key={h} style={{ fontSize: 9, color: 'var(--color-text-tertiary)', textAlign: 'center', paddingBottom: 2 }}>
            {h % 4 === 0 ? `${h}h` : ''}
          </div>
        ))}
        {/* Rows */}
        {days.map(day => (
          <>
            <div key={`label-${day}`} style={{ fontSize: 11, color: 'var(--color-text-tertiary)', display: 'flex', alignItems: 'center' }}>{day}</div>
            {hours.map(h => {
              const val = data[day]?.[String(h)] || 0
              const intensity = val / maxVal
              const bg = val === 0
                ? 'var(--color-bg-elevated)'
                : `rgba(239, 68, 68, ${0.15 + intensity * 0.85})`
              return (
                <div
                  key={`${day}-${h}`}
                  className="heatmap-cell"
                  style={{ height: 18, background: bg }}
                  title={`${day} ${h}:00 — ${val} failures`}
                />
              )
            })}
          </>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, fontSize: 11, color: 'var(--color-text-tertiary)' }}>
        <span>0 failures</span>
        {[0.1, 0.3, 0.6, 1.0].map(i => (
          <div key={i} style={{ width: 16, height: 16, borderRadius: 3, background: `rgba(239,68,68,${0.15 + i * 0.85})` }} />
        ))}
        <span>Max failures</span>
      </div>
    </div>
  )
}
