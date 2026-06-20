'use client'

import Link from 'next/link'

const FEATURES = [
  { icon: '⚡', title: 'Real-time Monitoring', desc: 'Webhook-driven ingestion of every workflow run the moment it happens.' },
  { icon: '🤖', title: 'AI Root Cause Analysis', desc: 'GPT-4o analyzes failures and returns structured root cause, evidence, and fixes in seconds.' },
  { icon: '📊', title: 'DORA Metrics', desc: 'Deployment frequency, MTTR, failure rate — all computed automatically.' },
  { icon: '🔍', title: 'Log Intelligence', desc: '100k+ line log viewer with semantic error extraction and full-text search.' },
  { icon: '🔔', title: 'Smart Notifications', desc: 'Slack, Teams, and email alerts with deduplication and severity routing.' },
  { icon: '🏥', title: 'Health Scoring', desc: 'Composite pipeline health score (0–100) per repo, updated after every run.' },
]

const HOW_IT_WORKS = [
  { step: '01', title: 'Connect Repositories', desc: 'Install the GitHub App or authenticate with OAuth. RavenOps automatically registers webhooks and syncs your workflow history.' },
  { step: '02', title: 'Automatic Analysis', desc: 'Every completed run triggers log download, semantic parsing, and AI-powered root cause analysis — no configuration needed.' },
  { step: '03', title: 'Ship With Confidence', desc: 'Executive dashboards, trend analytics, and actionable fix suggestions help your team reduce MTTR from hours to minutes.' },
]

export default function LandingPage() {
  return (
    <div className="hero-gradient" style={{ minHeight: '100vh', overflow: 'auto' }}>
      {/* Navigation */}
      <nav style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '20px 48px', borderBottom: '1px solid var(--color-border-subtle)',
        backdropFilter: 'blur(12px)', position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(10,10,11,0.8)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, var(--color-accent), var(--color-accent-dim))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 16px rgba(34,197,94,0.4)',
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M21 3L14.5 8.5 12 6l-9 9 2 2 7-7 2.5 2.5L8 19l2 2 8-8-2.5-2.5L21 3z"/></svg>
          </div>
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em' }}>RavenOps</span>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-accent)', background: 'var(--color-accent-muted)', padding: '2px 8px', borderRadius: 100, border: '1px solid rgba(34,197,94,0.2)' }}>Beta</span>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Link href="/dashboard"><button className="btn btn-secondary btn-sm" id="btn-nav-dashboard">Dashboard</button></Link>
          <Link href="/login"><button className="btn btn-primary btn-sm" id="btn-nav-login">Get Started →</button></Link>
        </div>
      </nav>

      {/* Hero */}
      <section style={{ textAlign: 'center', padding: '100px 48px 80px', maxWidth: 900, margin: '0 auto' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 100, background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)', marginBottom: 32 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-ai-end)', animation: 'pulse 2s infinite' }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-ai-end)' }}>Powered by GPT-4o — AI-native CI/CD observability</span>
        </div>
        <h1 className="hero-title-gradient animate-fade-in" style={{ fontSize: 'clamp(40px, 6vw, 72px)', fontWeight: 800, lineHeight: 1.05, letterSpacing: '-0.03em', marginBottom: 28 }}>
          See Every Pipeline.<br/>Understand Every Failure.
        </h1>
        <p className="animate-fade-in stagger-1" style={{ fontSize: 20, color: 'var(--color-text-secondary)', lineHeight: 1.6, marginBottom: 48, maxWidth: 640, margin: '0 auto 48px' }}>
          RavenOps connects to GitHub Actions and autonomously analyzes CI/CD failures with AI — delivering root cause, suggested fixes, and trend intelligence in seconds.
        </p>
        <div className="animate-fade-in stagger-2" style={{ display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link href="/login">
            <button className="btn btn-primary btn-lg" id="btn-hero-cta" style={{ gap: 10 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              Connect GitHub
            </button>
          </Link>
          <Link href="/dashboard">
            <button className="btn btn-secondary btn-lg" id="btn-hero-demo">View Dashboard →</button>
          </Link>
        </div>

        {/* Live terminal animation */}
        <div className="animate-fade-in stagger-3" style={{ marginTop: 72, textAlign: 'left', background: '#080809', border: '1px solid var(--color-border)', borderRadius: 16, padding: '24px', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.7, maxWidth: 700, margin: '72px auto 0' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#FF5F57' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#FEBC2E' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#28C840' }} />
          </div>
          <div style={{ color: '#666' }}>$ ravenops analyze --run 12847</div>
          <div style={{ color: 'var(--color-text-secondary)', marginTop: 8 }}>⠸ Fetching logs from GitHub Actions...</div>
          <div style={{ color: 'var(--color-text-secondary)' }}>⠸ Running semantic parser (45,213 lines)</div>
          <div style={{ color: 'var(--color-text-secondary)' }}>⠸ Sending to GPT-4o for analysis...</div>
          <div style={{ marginTop: 12, color: 'var(--color-success)' }}>✓ Analysis complete (2.3s)</div>
          <div style={{ marginTop: 8, color: 'var(--color-error)' }}>  ROOT CAUSE: npm dependency resolution failure</div>
          <div style={{ color: '#A855F7' }}>  SEVERITY: HIGH | CONFIDENCE: 92%</div>
          <div style={{ color: 'var(--color-text-secondary)', marginTop: 4 }}>  FIX: npm install @tanstack/react-query@latest</div>
          <div style={{ color: 'var(--color-text-tertiary)' }}>  EFFORT: minutes | RECURRENCE: 3× in 7 days</div>
        </div>
      </section>

      {/* Features */}
      <section style={{ padding: '80px 48px', maxWidth: 1100, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: 36, fontWeight: 800, letterSpacing: '-0.025em', marginBottom: 60 }}>
          Everything your team needs to <span style={{ color: 'var(--color-accent)' }}>ship faster</span>
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 24 }}>
          {FEATURES.map((f, i) => (
            <div key={f.title} className={`card animate-fade-in stagger-${i + 1}`} style={{ padding: 28 }}>
              <div style={{ fontSize: 32, marginBottom: 16 }}>{f.icon}</div>
              <h3 style={{ fontSize: 17, fontWeight: 700, marginBottom: 10, color: 'var(--color-text-primary)' }}>{f.title}</h3>
              <p style={{ fontSize: 14, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section style={{ padding: '40px 48px 100px', maxWidth: 900, margin: '0 auto' }}>
        <h2 style={{ textAlign: 'center', fontSize: 36, fontWeight: 800, letterSpacing: '-0.025em', marginBottom: 60 }}>How it works</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
          {HOW_IT_WORKS.map(step => (
            <div key={step.step} style={{ display: 'flex', gap: 32, alignItems: 'flex-start' }}>
              <div style={{
                fontSize: 13, fontWeight: 800, color: 'var(--color-accent)',
                background: 'var(--color-accent-muted)', border: '1px solid rgba(34,197,94,0.2)',
                borderRadius: 10, padding: '8px 14px', flexShrink: 0, fontFamily: 'var(--font-mono)',
              }}>{step.step}</div>
              <div>
                <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>{step.title}</h3>
                <p style={{ fontSize: 15, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--color-border)', padding: '32px 48px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--color-text-tertiary)', fontSize: 13 }}>
        <span>© 2024 RavenOps. Built for platform engineering teams.</span>
        <div style={{ display: 'flex', gap: 24 }}>
          <a href="#" style={{ color: 'var(--color-text-tertiary)' }}>Docs</a>
          <a href="#" style={{ color: 'var(--color-text-tertiary)' }}>GitHub</a>
          <a href="#" style={{ color: 'var(--color-text-tertiary)' }}>Status</a>
        </div>
      </footer>
    </div>
  )
}
