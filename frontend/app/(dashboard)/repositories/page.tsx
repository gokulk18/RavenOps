'use client'

import { useState } from 'react'
import Topbar from '@/components/Topbar'
import { useApi, apiFetch } from '@/lib/utils'
import { EmptyState } from '@/components/ui'
import Link from 'next/link'

interface Repository {
  id: string
  name: string
  full_name: string
  description: string
  language: string
  default_branch: string
  connected_at: string
  sync_status: string
}

interface GitHubRepo {
  github_repo_id: number
  name: string
  full_name: string
  description: string
  language: string
  default_branch: string
  private: boolean
  html_url: string
  connected: boolean
}

interface ReposResponse {
  repos: Repository[]
  total: number
}

interface GitHubReposResponse {
  repos: GitHubRepo[]
  total: number
}

export default function RepositoriesPage() {
  const [activeTab, setActiveTab] = useState<'connected' | 'import'>('connected')
  
  // Fetch connected repos
  const { data: connectedData, loading: loadingConnected, mutate: mutateConnected } = useApi<ReposResponse>('/repos')
  
  // Fetch user repos from GitHub API
  const { data: githubData, loading: loadingGithub, error: githubError, mutate: mutateGithub } = useApi<GitHubReposResponse>(
    activeTab === 'import' ? '/repos/github' : null
  )

  const [connectingRepoId, setConnectingRepoId] = useState<number | null>(null)
  const [message, setMessage] = useState('')

  async function handleConnect(fullName: string, repoId: number) {
    setConnectingRepoId(repoId)
    setMessage('')
    try {
      const res = await apiFetch('/repos/connect', {
        method: 'POST',
        body: JSON.stringify({ full_name: fullName }),
      })
      if (!res.ok) {
        const body = await res.json()
        throw new Error(body.detail || 'Failed to connect repository')
      }
      setMessage(`Successfully enabled observability for ${fullName}!`)
      
      // Refresh both states
      setTimeout(() => {
        setMessage('')
        if (mutateConnected) mutateConnected()
        if (mutateGithub) mutateGithub()
      }, 1500)
    } catch (e: any) {
      alert(e.message)
    } finally {
      setConnectingRepoId(null)
    }
  }

  return (
    <>
      <Topbar title="Code Repositories" />
      <main className="page-content">
        {/* Navigation Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--color-border)', marginBottom: 'var(--space-6)', gap: 24 }}>
          <button
            onClick={() => setActiveTab('connected')}
            style={{
              padding: '12px 4px',
              fontSize: 'var(--text-sm)',
              fontWeight: 700,
              background: 'none',
              border: 'none',
              color: activeTab === 'connected' ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              borderBottom: activeTab === 'connected' ? '2px solid var(--color-accent)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Connected Repositories ({connectedData?.total || 0})
          </button>
          <button
            onClick={() => setActiveTab('import')}
            style={{
              padding: '12px 4px',
              fontSize: 'var(--text-sm)',
              fontWeight: 700,
              background: 'none',
              border: 'none',
              color: activeTab === 'import' ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              borderBottom: activeTab === 'import' ? '2px solid var(--color-accent)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Import from GitHub
          </button>
        </div>

        {message && (
          <div style={{ padding: '12px 16px', background: 'var(--color-success-muted)', border: '1px solid var(--color-success)', color: 'var(--color-success)', borderRadius: 6, fontSize: 'var(--text-sm)', marginBottom: 'var(--space-5)' }}>
            {message}
          </div>
        )}

        {/* Tab 1: Connected Repositories */}
        {activeTab === 'connected' && (
          loadingConnected ? (
            <div className="grid grid-3">
              <div className="skeleton" style={{ height: 160 }} />
              <div className="skeleton" style={{ height: 160 }} />
              <div className="skeleton" style={{ height: 160 }} />
            </div>
          ) : connectedData && connectedData.repos.length > 0 ? (
            <div className="grid grid-3">
              {connectedData.repos.map(repo => (
                <div key={repo.id} className="card hover-scale animate-fade-in" style={{ padding: 'var(--space-6)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
                    <div className="font-mono" style={{ fontSize: 11, color: 'var(--color-accent)', padding: '2px 6px', background: 'var(--color-accent-muted)', borderRadius: 4 }}>
                      {repo.language || 'Unknown'}
                    </div>
                    <span className="badge badge-success">Active</span>
                  </div>
                  <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, margin: '0 0 8px 0', color: 'var(--color-text-primary)' }}>
                    {repo.name}
                  </h3>
                  <p className="font-sans" style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)', minHeight: 40, margin: '0 0 16px 0', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {repo.description || 'No description provided.'}
                  </p>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>
                    <span>Connected {new Date(repo.connected_at).toLocaleDateString()}</span>
                    <Link href={`/repositories/${repo.id}`} className="btn btn-ghost btn-sm" style={{ paddingRight: 0 }}>
                      Configure →
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No Connected Repositories"
              description="Monitor your builds and logs in real-time. Link repos from your GitHub profile to start."
              action={
                <button className="btn btn-primary" onClick={() => setActiveTab('import')}>
                  Browse GitHub Repositories
                </button>
              }
            />
          )
        )}

        {/* Tab 2: Import from GitHub (OAuth List) */}
        {activeTab === 'import' && (
          loadingGithub ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="skeleton" style={{ height: 60 }} />
              <div className="skeleton" style={{ height: 60 }} />
              <div className="skeleton" style={{ height: 60 }} />
            </div>
          ) : githubError ? (
            <EmptyState
              title="OAuth Connection Required"
              description="We could not access your GitHub profile. Please re-authenticate to sync your repositories."
              action={
                <button className="btn btn-primary" onClick={() => window.location.href = '/login'}>
                  Re-Authenticate with GitHub
                </button>
              }
            />
          ) : githubData && githubData.repos.length > 0 ? (
            <div className="card" style={{ padding: 'var(--space-4) 0' }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {githubData.repos.map((repo, idx) => (
                  <div
                    key={repo.github_repo_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px 24px',
                      borderBottom: idx === githubData.repos.length - 1 ? 'none' : '1px solid var(--color-border)',
                      transition: 'background 0.2s ease',
                    }}
                    className="hover-bg"
                  >
                    <div style={{ flex: 1, minWidth: 0, paddingRight: 16 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontSize: 'var(--text-sm)' }}>
                          {repo.full_name}
                        </span>
                        <span className="badge badge-muted" style={{ fontSize: 9 }}>
                          {repo.private ? 'Private' : 'Public'}
                        </span>
                        {repo.language && (
                          <span style={{ fontSize: 10, color: 'var(--color-text-secondary)', background: 'var(--color-bg-muted)', padding: '2px 6px', borderRadius: 4 }}>
                            {repo.language}
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {repo.description || 'No description provided.'}
                      </p>
                    </div>

                    <div>
                      {repo.connected ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-accent)', fontWeight: 600, fontSize: 'var(--text-xs)' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                          Observability Active
                        </div>
                      ) : (
                        <button
                          className="btn btn-outline btn-sm"
                          disabled={connectingRepoId === repo.github_repo_id}
                          onClick={() => handleConnect(repo.full_name, repo.github_repo_id)}
                        >
                          {connectingRepoId === repo.github_repo_id ? 'Enabling...' : 'Enable Observability'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState
              title="No Repositories Found"
              description="No repositories were found on your GitHub account."
            />
          )
        )}
      </main>
    </>
  )
}
