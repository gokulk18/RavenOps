# RavenOps — AI-Powered CI/CD Observability & RCA

RavenOps is a microservice platform that monitors your GitHub Actions pipelines, automatically downloads and parses failure logs, and runs structured AI Root Cause Analysis (RCA) on failed runs to suggest immediate engineering fixes.

---

## How to Set Up & Use the Application (Real-Time Guide)

To use this application in your development environment with **real-time** data, you need to configure a GitHub App and set up webhook forwarding to your local machine.

### Step 1: Create a GitHub App
1. Go to your GitHub account **Settings** -> **Developer Settings** -> **GitHub Apps** -> **New GitHub App**.
2. Fill in the following details:
   * **GitHub App name**: `RavenOps-Dev-<your-name>`
   * **Homepage URL**: `http://localhost:3000`
   * **Webhook**: Check **Active**.
   * **Webhook URL**: *(We will set this using a webhook forwarding service in Step 2)*.
   * **Webhook Secret**: Choose a secret string (e.g. `ravenops-webhook-secret-local`).
3. Set the following permissions:
   * **Repository Permissions**:
     * **Actions**: `Read-only` (to fetch pipeline runs and logs).
     * **Metadata**: `Read-only` (basic repository info).
     * **Checks**: `Read-only` (to inspect run status).
   * **Organization Permissions** (if installing on an Org):
     * **Members**: `Read-only`.
4. Under **Subscribe to events**, select:
   * **Workflow run** (triggers analysis when runs start/finish).
   * **Workflow job** (updates step details and execution status).
5. Click **Create GitHub App**.
6. Save the **App ID**, **Client ID**, and generate a **Client Secret**.
7. Scroll down to **Private keys** and click **Generate a private key**. A `.pem` file will download to your computer.

---

### Step 2: Configure Webhook Forwarding (smee.io or ngrok)

GitHub webhooks cannot send events directly to your local `localhost:8000` port. You need a tunnel:

#### Option A: Smee.io (Recommended & Easiest)
1. Go to [smee.io](https://smee.io/) and click **Start a new channel**.
2. Copy the unique Smee channel URL (e.g., `https://smee.io/abc123XYZ`).
3. Go back to your GitHub App settings and paste this Smee URL into the **Webhook URL** field.
4. Install the Smee CLI client globally:
   ```bash
   npm install --global smee-client
   ```
5. Start the forwarder in a terminal window (redirects to the API Gateway port):
   ```bash
   smee --url https://smee.io/abc123XYZ --path /webhooks/receive --port 8000
   ```

#### Option B: Ngrok
1. Start an ngrok tunnel on the API Gateway port:
   ```bash
   ngrok http 8000
   ```
2. Copy the public forwarding HTTPS URL (e.g. `https://1234-abcd.ngrok-free.app`).
3. Update your GitHub App **Webhook URL** to `https://1234-abcd.ngrok-free.app/webhooks/receive`.

---

### Step 3: Populate Environment Variables (`.env`)

In the root [d:\RavenOps\.env](file:///d:/RavenOps/.env) file (and optionally in [d:\RavenOps\frontend\.env](file:///d:/RavenOps/frontend/.env)), update the following placeholders with your GitHub App credentials:

```env
# GitHub Auth & API Credentials
GITHUB_APP_ID=your_github_app_id
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Paste the content of the downloaded .pem private key file as a single line (replacing newlines with \n) 
# or direct reference.
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"

# Webhook Secret from Step 1
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# OAuth Redirect URL (must match the Callback URL in GitHub App Settings)
GITHUB_REDIRECT_URI=http://localhost:3000/login
```

---

### Step 4: Run the Application

Now restart the services to load the new environment variables:
```bash
docker-compose down
docker-compose up --build -d
```

---

### Step 5: How to Test the Flow

1. Open your browser and navigate to the frontend portal: **`http://localhost:3000`**.
2. Click **"Continue with GitHub"** to authenticate via OAuth.
3. Once logged in, go to the **Repositories** tab and click **Connect Repository**.
4. Input your repository's full name (e.g., `your-github-username/your-repo`) and submit.
5. In your connected repository:
   * Make a commit that triggers a GitHub Actions workflow that fails (e.g. add a step `run: exit 1` or a failing test).
6. **Watch the Magic**:
   * The workflow starts -> GitHub triggers a webhook -> forwarded via Smee/ngrok to `api-gateway` -> processed by `github-service`.
   * The run fails -> `workflow-service` catches it and notifies the pipeline queue.
   * `log-service` downloads the run logs, parses the errors, and uploads them.
   * `ai-service` sends the error context to OpenAI/mock AI and generates a root-cause explanation.
   * Open the **Dashboard** or **AI Insights** tabs at `http://localhost:3000` to inspect the analysis, failure chain, and recommended fixes in real-time!
