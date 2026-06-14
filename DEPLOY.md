# DEPLOY — Ask Territory on Oracle Cloud Always Free

**Total cost: $0/month** (Oracle Always Free) + ~$15–20/year (domain).

This guide takes you from zero to a live HTTPS website running the full stack —
web app, Form Finder, How-To Hub, and the AI-powered chat (hosted API) — on
Oracle Cloud's permanently free ARM instance.

---

## What you get with Oracle Always Free

| Resource | Free allowance | What we use it for |
|----------|---------------|-------------------|
| VM.Standard.A1.Flex | **4 ARM vCPU · 24 GB RAM** | Web app (the AI is hosted; far less RAM needed now) |
| Block storage | **200 GB** | OS + code + SQLite databases |
| Bandwidth out | **10 TB/month** | More than enough for a council site |
| Public IP | 1 static IP | Your server address |
| Duration | **Forever** | No expiry, no credit card charge after signup |

> **Note:** Oracle asks for a credit card at signup to verify identity. You will
> **not** be charged as long as you stay on Always Free resources. Set a billing
> alert at $1 for peace of mind.

---

## Overview — five steps

```
1. Oracle account + VM         (~20 min, one-time)
2. Domain + Cloudflare DNS     (~15 min, one-time)
3. Server setup + code         (~15 min, one-time)
4. Run the app + AI model      (~10 min + model download)
5. Seed the databases          (~30–90 min scraping)
```

---

## Step 1 — Create the Oracle Cloud VM

### 1a — Sign up

1. Go to **https://signup.cloud.oracle.com**
2. Choose your **Home Region** — pick the closest to Darwin:
   - `ap-sydney-1` (Sydney) — best latency for NT
   - `ap-melbourne-1` (Melbourne) — alternative
   > ⚠ You **cannot change** your Home Region after signup. Pick Sydney.
3. Complete signup — enter credit card for identity verification only.
4. Wait for the "Your account is ready" email (usually a few minutes, sometimes up to 24h).

### 1b — Create the VM instance

1. Log in → **Compute → Instances → Create Instance**
2. **Name:** `ask-territory`
3. **Image:** Click *Change Image* → select **Canonical Ubuntu** → `22.04 Minimal`
4. **Shape:** Click *Change Shape*:
   - Select **Ampere** (ARM)
   - Shape: `VM.Standard.A1.Flex`
   - Set **OCPUs: 4**, **Memory: 24 GB**
   > This is the Always Free shape. Anything else may incur charges.
5. **Networking:** Leave defaults (a VCN and public subnet will be auto-created)
6. **SSH keys:**
   - If you have an SSH key pair: paste your **public key** (`~/.ssh/id_rsa.pub`)
   - If not: click *Save Private Key* to download one — keep it safe
7. **Boot volume:** 100 GB (free up to 200 GB total across all instances)
8. Click **Create**

Wait ~2 minutes. Note the **Public IP address** shown on the instance page.

### 1c — Open firewall ports in Oracle's Security List

Oracle has its own firewall (Security Lists) on top of the OS firewall:

1. Go to **Networking → Virtual Cloud Networks → your VCN → Security Lists → Default**
2. Click **Add Ingress Rules** and add two rules:

| Stateless | Source | Protocol | Port |
|-----------|--------|----------|------|
| No | 0.0.0.0/0 | TCP | 80 |
| No | 0.0.0.0/0 | TCP | 443 |

3. Click **Add Ingress Rules** — done.

### 1d — Connect to your server

```bash
# replace with your actual key path and IP
ssh -i ~/.ssh/your-key.pem ubuntu@<your-oracle-public-ip>
```

---

## Step 2 — Domain + Cloudflare (free CDN + SSL)

Using Cloudflare in front of your Oracle IP gives you:
- Free SSL/HTTPS certificate (no certbot needed)
- DDoS protection
- Global edge caching
- Hides your server IP from the public internet

### 2a — Register a domain

Buy a domain from any registrar. Suggestions for this project:
- `askterritory.com.au` (~$20/yr — Australian, looks official)
- `ntforms.com.au` (~$20/yr)
- `askdarwin.com.au` (~$20/yr)

Recommended registrar: **Namecheap** or **Cloudflare Registrar** (at-cost pricing).

### 2b — Add site to Cloudflare

1. Create a free account at **https://cloudflare.com**
2. Click **Add a Site** → enter your domain → choose **Free plan**
3. Cloudflare shows you two nameservers, e.g.:
   ```
   alex.ns.cloudflare.com
   nina.ns.cloudflare.com
   ```
4. Go to your domain registrar → find **Nameservers** → replace them with Cloudflare's two
5. Wait 5–30 minutes for propagation

### 2c — Add DNS records in Cloudflare

In Cloudflare → DNS → Records → **Add record**:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `@` | `<your Oracle public IP>` | ✅ Proxied (orange cloud) |
| A | `www` | `<your Oracle public IP>` | ✅ Proxied |

### 2d — Set SSL mode

Cloudflare → SSL/TLS → Overview → set to **Full** (not Flexible).

That's it — Cloudflare handles HTTPS automatically. No certbot, no Let's Encrypt renewal to manage.

---

## Step 3 — Server setup + code

SSH into your Oracle VM (`ssh -i key.pem ubuntu@<ip>`), then run:

### 3a — OS firewall (Ubuntu's ufw)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

> Oracle Security List handles the outer firewall; ufw handles the OS layer.
> Both need the ports open.

### 3b — Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# log out and back in so group takes effect
exit
ssh -i ~/.ssh/your-key.pem ubuntu@<ip>
```

### 3c — Clone the repository

```bash
sudo apt install -y git
git clone https://github.com/Yasin54386/agentic-ai-local-gov.git /opt/ask-territory
cd /opt/ask-territory
```

### 3d — Configure environment

```bash
cp .env.example .env
nano .env
```

Edit these values:

```bash
DOMAIN=yourdomain.com.au          # your actual domain
LETSENCRYPT_EMAIL=you@email.com   # not used with Cloudflare but keep it set
ANTHROPIC_API_KEY=sk-...          # the hosted AI key (keep this secret)
MODEL=claude-haiku-4-5            # provider-neutral in the UI
BUDGET_MONTHLY_AUD=100            # hard monthly spend ceiling
```

Save with `Ctrl+O`, exit with `Ctrl+X`.

### 3e — Configure nginx for your domain

```bash
sudo apt install -y nginx

# Copy and customise the site config
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ask-territory
sudo sed -i "s/ask-territory.com.au/yourdomain.com.au/g" \
    /etc/nginx/sites-available/ask-territory
sudo ln -sf /etc/nginx/sites-available/ask-territory \
    /etc/nginx/sites-enabled/ask-territory
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t                     # should say: syntax is ok
sudo systemctl enable nginx
sudo systemctl restart nginx
```

> Cloudflare talks HTTP to your origin on port 80 (SSL is terminated at Cloudflare).
> The nginx config handles this correctly — citizens always see HTTPS.

---

## Step 4 — Run the app

The AI is hosted, so there is no model server to run or model to download — the
box just needs the web app. (A small instance is plenty now; the old 24 GB
requirement was only for running a model locally.)

### 4a — Apply database migrations

```bash
cd /opt/ask-territory
python3 -m db.migrate
```

### 4b — Start the stack

```bash
sudo docker compose up -d --build
```

This starts:
- **web** — the Ask Territory app on `127.0.0.1:8000`
- (optional) **refresh** — add `--profile refresh` for the 6-hourly data job

### 4c — Confirm the AI chat is configured

```bash
# Reads ANTHROPIC_API_KEY from your .env; "true" means chat is live.
curl -s http://localhost:8000/api/health | grep -o '"ai_available":[a-z]*'
```

If the key is missing, the chat shows offline and every data tab still works.

### 4d — Verify everything is running

```bash
# App health check
curl -s localhost:8000/api/health
# Expected: {"ok": true, "ai_available": true, ...}

# Check all containers
sudo docker compose ps
# All should show "running"
```

### 4e — Check it's publicly accessible

Open a browser and visit `https://yourdomain.com.au` — you should see Ask Territory.

If you see a Cloudflare error, wait 5 more minutes for DNS to fully propagate.

---

## Step 5 — Seed the databases (scraping)

This is what builds the Form Finder and How-To Hub content.

```bash
cd /opt/ask-territory

# Seed government forms (~20–40 min, target 1,000+ forms)
python3 scripts/scrape_forms.py

# Seed how-to guides (~30–60 min, target 1,000+ guides)
python3 scripts/scrape_howto.py
```

Run these in a `tmux` or `screen` session so they survive if SSH disconnects:

```bash
# Install tmux (if not already there)
sudo apt install -y tmux

# Start a session
tmux new -s scrape

# Run scrapers
python3 scripts/scrape_forms.py && python3 scripts/scrape_howto.py

# Detach with Ctrl+B then D — scraping continues in background
# Reattach later with: tmux attach -t scrape
```

### Schedule weekly re-scrapes, link checks, and backups (cron)

```bash
crontab -e
```

Add at the bottom:

```cron
# Re-scrape NT government forms and how-to guides every Sunday at 2am
0 2 * * 0 cd /opt/ask-territory && python3 scripts/scrape_forms.py >> /var/log/scrape.log 2>&1
30 2 * * 0 cd /opt/ask-territory && python3 scripts/scrape_howto.py >> /var/log/scrape.log 2>&1

# Check for dead links and remove them — Monday at 3am (after scrape completes)
0 3 * * 1 cd /opt/ask-territory && python3 scripts/check_links.py >> /var/log/linkcheck.log 2>&1

# Weekly database backup — Sunday at 1am (before scrape, so we keep a clean copy)
0 1 * * 0 cd /opt/ask-territory && bash scripts/backup_db.sh >> /var/log/backup.log 2>&1
```

The backup script keeps 30 days of backups and auto-deletes older ones.
Backups go to `/opt/ask-territory/backups/` — consider copying them off-server too:

```bash
# Optional: copy latest backup to another machine after each backup
# Add to the cron line: && scp backups/askterritory_*.sql.gz user@backup-server:/backups/
```

---

## Day-to-day operations

| Task | Command |
|------|---------|
| View live logs | `sudo docker compose logs -f web` |
| Restart app | `sudo docker compose restart web` |
| Pull code update | `git pull && sudo docker compose up -d --build` |
| Stop everything | `sudo docker compose down` |
| Check disk usage | `df -h` |
| Check RAM usage | `free -h` |
| Check form count | `python3 -c "import sqlite3; db=sqlite3.connect('data/askterritory.db'); print(db.execute('SELECT COUNT(*) FROM forms').fetchone()[0], 'forms')"` |
| Check howto count | `python3 -c "import sqlite3; db=sqlite3.connect('data/askterritory.db'); print(db.execute('SELECT COUNT(*) FROM howto_guides').fetchone()[0], 'guides')"` |

---

## Troubleshooting

**Site shows Cloudflare error 522 (connection timed out)**
- The app isn't running. Check: `sudo docker compose ps` and `sudo docker compose logs web`
- Make sure nginx is running: `sudo systemctl status nginx`
- Make sure Oracle Security List has ports 80 and 443 open

**App running but AI chat not working**
- Key not set: check `ANTHROPIC_API_KEY` is in `.env`, then `sudo docker compose up -d`
- Confirm: `curl -s localhost:8000/api/health | grep ai_available` → should be `true`
- Budget reached: `curl -s localhost:8000/api/budget` — if `state` is `paused`, the
  monthly/daily cap is hit and chat resumes automatically (data tabs keep working)

**Running out of disk space**
- Check: `df -h` and `du -sh /opt/ask-territory/data/*`
- Oracle gives 200 GB free — you can expand the boot volume in the OCI console at no charge

**SSH connection refused after reboot**
- Oracle VMs restart cleanly. Docker auto-restarts containers (`restart: unless-stopped` in compose).
- If nginx didn't restart: `sudo systemctl start nginx`

**Want a higher-quality model later**
```bash
# Edit .env: MODEL=claude-sonnet-4-6   (higher quality, higher per-call cost —
# the monthly budget cap still applies, so chat just pauses sooner if it's hit)
sudo docker compose up -d
```

---

## Architecture summary

```
Citizen browser (anywhere)
        │
        │ HTTPS — Cloudflare terminates SSL, caches static pages
        ▼
  Cloudflare Edge (free)
        │
        │ HTTP port 80 — proxied, origin IP hidden
        ▼
  Oracle ARM VM · ap-sydney-1 · Always Free
  ├── nginx          (port 80 → proxy to 8000; rate-limits /api/ask)
  ├── Docker: web    (port 8000, Ask Territory app → hosted AI API)
  ├── Docker: refresh(optional 6-hourly data sync)
  └── SQLite files   (/opt/ask-territory/data/*.db)
        ├── forms        (Form Finder — 1,000+ scraped forms)
        ├── howto_guides (How-To Hub — 1,000+ guides)
        └── records      (live weather, flood, open datasets)
```

---

## Cost breakdown

| Item | Cost |
|------|------|
| Oracle Cloud VM (4 vCPU · 24 GB · 200 GB) | **$0/month** |
| Cloudflare (CDN + DDoS + SSL) | **$0/month** |
| Domain (`yourdomain.com.au`) | ~$20/year |
| Hosted AI chat | **≤ $100 AUD/month** (hard budget cap; most traffic is token-free) |
| **Total** | **~$20/year + capped AI spend** |

---

## Pre-launch checklist

- [ ] Oracle VM created — shape `VM.Standard.A1.Flex`, 4 OCPU, 24 GB, Ubuntu 22.04
- [ ] Oracle Security List — ports 80 and 443 open
- [ ] Domain registered and nameservers pointing to Cloudflare
- [ ] Cloudflare DNS A records point to Oracle public IP (proxied)
- [ ] Cloudflare SSL mode set to Full
- [ ] ufw firewall enabled on the VM
- [ ] Docker installed and `docker compose up -d` running
- [ ] `ANTHROPIC_API_KEY` set in `.env`
- [ ] `curl localhost:8000/api/health` returns `{"ok": true, "ai_available": true}`
- [ ] `https://yourdomain.com.au` loads in browser
- [ ] Forms scraper run — `SELECT COUNT(*) FROM forms` shows data
- [ ] How-To scraper run — `SELECT COUNT(*) FROM howto_guides` shows data
- [ ] Weekly cron scrape scheduled
- [ ] Billing alert set at $1 in OCI console (belt-and-braces)
