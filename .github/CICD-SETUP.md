# CI/CD Setup — GitHub Actions → Oracle Cloud

The workflow in `.github/workflows/deploy.yml` runs automatically on every
push to `main`. It:
1. Syntax-checks all Python files
2. Runs database migrations as a smoke test
3. SSHes into your Oracle VM and does a zero-downtime redeploy
4. Waits for the health endpoint to confirm the app is up

## One-time setup (5 minutes)

### Step 1 — Add GitHub Secrets

Go to your repo on GitHub:
**Settings → Secrets and variables → Actions → New repository secret**

Add these four secrets:

| Secret name | Value |
|-------------|-------|
| `ORACLE_HOST` | Your Oracle VM's public IP (e.g. `129.154.x.x`) |
| `ORACLE_USER` | `ubuntu` (Oracle Ubuntu VMs use this by default) |
| `ORACLE_SSH_KEY` | Full contents of your private key file (the `.pem` file) — paste the entire text including `-----BEGIN...` and `-----END...` lines |
| `ORACLE_DEPLOY_DIR` | `/opt/ask-territory` |

### Step 2 — Add GitHub's SSH key to your Oracle VM

GitHub Actions needs to SSH into your Oracle VM. Make sure the public key that
matches your `ORACLE_SSH_KEY` is in the VM's `~/.ssh/authorized_keys`.

If you used Oracle's auto-generated key at VM creation, it's already there.
If you're using a new key pair:

```bash
# On your local machine — copy public key to the VM
ssh-copy-id -i ~/.ssh/your-key.pub ubuntu@<oracle-ip>
```

### Step 3 — Make sure the VM can pull from GitHub

SSH into your Oracle VM and verify:

```bash
ssh -i key.pem ubuntu@<oracle-ip>
cd /opt/ask-territory
git fetch origin main    # should work without a password prompt
```

If the repo is private, you need to either:
- Use HTTPS with a GitHub Personal Access Token (PAT):
  ```bash
  git remote set-url origin https://<PAT>@github.com/Yasin54386/agentic-ai-local-gov.git
  ```
- Or add a deploy SSH key to the repo (GitHub repo Settings → Deploy keys)

---

## How the pipeline works

```
git push to main
      │
      ▼
GitHub Actions runner (ubuntu-latest)
  ├── Checkout code
  ├── Syntax check all .py files
  ├── Run db.migrate (smoke test)
  ├── Verify tables and routes exist
  │
  └── (if all pass) SSH into Oracle VM
          ├── git fetch + reset --hard origin/main
          ├── python3 -m db.migrate        (apply any new migrations)
          ├── docker compose up -d --build  (rebuild changed layers only)
          └── poll /api/health until OK
```

**Zero-downtime:** Docker Compose brings up the new container before stopping
the old one. The app stays available during deploys.

**Rollback:** If the new code fails the health check, the old container is still
running. SSH in and run `git revert` or `git reset`, then redeploy.

---

## Triggering a manual deploy

You don't have to push code to deploy. You can trigger from the GitHub UI:

**Actions tab → Deploy to Oracle Cloud → Run workflow → Run workflow**

Useful if you've made changes directly on the server (e.g. updated `.env`)
and want to resync without a code change.

---

## Monitoring

After a push, watch the pipeline:
**GitHub → Actions tab → the latest "Deploy to Oracle Cloud" run**

Each step shows its output. The "Deploy to Oracle VM" step streams the full
remote output so you can see exactly what happened on the server.
