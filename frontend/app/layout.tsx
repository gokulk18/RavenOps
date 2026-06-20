import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: { default: 'RavenOps', template: '%s | RavenOps' },
  description: 'See Every Pipeline. Understand Every Failure. Ship Faster. AI-powered GitHub Actions intelligence and CI/CD observability platform.',
  keywords: ['CI/CD', 'GitHub Actions', 'DevOps', 'observability', 'pipeline intelligence', 'RCA'],
  authors: [{ name: 'RavenOps' }],
  openGraph: {
    title: 'RavenOps — CI/CD Intelligence Platform',
    description: 'AI-powered GitHub Actions observability. Reduce MTTR from hours to minutes.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
