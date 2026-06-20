// MongoDB initialization script for RavenOps
db = db.getSiblingDB('ravenops');

// ── Collections ──────────────────────────────────────────────────────
db.createCollection('users');
db.createCollection('organizations');
db.createCollection('refresh_tokens');
db.createCollection('audit_logs');
db.createCollection('repositories');
db.createCollection('workflow_definitions');
db.createCollection('workflow_runs');
db.createCollection('workflow_jobs');
db.createCollection('workflow_steps');
db.createCollection('logs_metadata');
db.createCollection('parsed_logs');
db.createCollection('ai_analysis');
db.createCollection('analytics_snapshots');
db.createCollection('notifications');

// ── Indexes ───────────────────────────────────────────────────────────
db.users.createIndex({ github_id: 1 }, { unique: true });
db.users.createIndex({ github_login: 1 }, { unique: true });
db.users.createIndex({ email: 1 }, { sparse: true });
db.users.createIndex({ is_active: 1 });

db.organizations.createIndex({ github_org_id: 1 }, { unique: true });
db.organizations.createIndex({ slug: 1 }, { unique: true });

db.refresh_tokens.createIndex({ user_id: 1 });
db.refresh_tokens.createIndex({ token_hash: 1 }, { unique: true });
db.refresh_tokens.createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 });

db.repositories.createIndex({ github_repo_id: 1 }, { unique: true });
db.repositories.createIndex({ owner_id: 1 });
db.repositories.createIndex({ full_name: 1 });
db.repositories.createIndex({ organization_id: 1 });
db.repositories.createIndex({ is_active: 1 });

db.workflow_definitions.createIndex({ github_workflow_id: 1 }, { unique: true });
db.workflow_definitions.createIndex({ repo_id: 1 });

db.workflow_runs.createIndex({ github_run_id: 1 }, { unique: true });
db.workflow_runs.createIndex({ repo_id: 1, created_at: -1 });
db.workflow_runs.createIndex({ workflow_id: 1, created_at: -1 });
db.workflow_runs.createIndex({ conclusion: 1 });
db.workflow_runs.createIndex({ status: 1 });
db.workflow_runs.createIndex({ head_branch: 1 });
db.workflow_runs.createIndex({ analysis_status: 1 });
db.workflow_runs.createIndex({ log_status: 1 });

db.workflow_jobs.createIndex({ github_job_id: 1 }, { unique: true });
db.workflow_jobs.createIndex({ run_id: 1 });
db.workflow_jobs.createIndex({ repo_id: 1 });

db.workflow_steps.createIndex({ job_id: 1 });
db.workflow_steps.createIndex({ run_id: 1 });

db.logs_metadata.createIndex({ run_id: 1 }, { unique: true });
db.logs_metadata.createIndex({ repo_id: 1 });
db.logs_metadata.createIndex({ status: 1 });

db.parsed_logs.createIndex({ run_id: 1 });
db.parsed_logs.createIndex({ repo_id: 1 });
db.parsed_logs.createIndex({ 'errors.fingerprint': 1 });

db.ai_analysis.createIndex({ run_id: 1 });
db.ai_analysis.createIndex({ repo_id: 1 });
db.ai_analysis.createIndex({ 'root_cause.category': 1 });
db.ai_analysis.createIndex({ 'severity.level': 1 });

db.analytics_snapshots.createIndex({ scope: 1, scope_id: 1, period: 1, period_start: -1 });
db.analytics_snapshots.createIndex({ computed_at: -1 });

db.notifications.createIndex({ user_id: 1, created_at: -1 });
db.notifications.createIndex({ repo_id: 1 });
db.notifications.createIndex({ read: 1 });

print('RavenOps MongoDB initialized successfully');
