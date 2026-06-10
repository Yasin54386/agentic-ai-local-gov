# Deploy Ask Territory to DigitalOcean

Push-to-deploy: once set up, every push to `main` runs the tests and, if they
pass, SSHes into your droplet and ships the new code automatically.

This guide is the **web-only** path (the AI chat shows "model offline" until you
size up). It runs comfortably on the cheapest droplet. Adding the self-hosted
model later is one extra step (bottom of this file).

---

## Step 1 — Create the droplet (in the DO web console)

1. **Create → Droplets**
2. Image: **Ubuntu 24.04 (LTS)**
3. Plan: **Basic → Regular → $6/mo (1 GB)** is enough for web-only; **$12/mo
   (2 GB)** gives Docker more build headroom (recommended).
4. Region: closest to your users (e.g. Sydney `SYD1`).
5. Authentication: **SSH key** — add the public key you'll deploy with. If you
   don't have one yet, on your laptop run `ssh-keygen -t ed25519 -C deploy` and
   paste the contents of `~/.ssh/id_ed25519.pub`.
6. Create. Note the **public IP**.

> The **private** key (`~/.ssh/id_ed25519`, the file *without* `.pub`) is what
> GitHub Actions will use — you'll paste it as a secret in Step 3.

## Step 2 — Provision the droplet (one time)

SSH in and run the provisioning script. It installs Docker + nginx, clones the
repo, builds the database, starts the web container, and puts nginx on port 80.

```bash
ssh root@YOUR_DROPLET_IP
curl -fsSL https://raw.githubusercontent.com/Yasin54386/agentic-ai-local-gov/main/deploy/provision-digitalocean.sh | bash
```

When it finishes, open `http://YOUR_DROPLET_IP/` — the site should be live.

## Step 3 — Add GitHub secrets (enables auto-deploy)

Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add these four:

| Secret | Value |
|---|---|
| `DO_HOST` | the droplet's public IP (or your domain) |
| `DO_USER` | `root` (or your sudo user) |
| `DO_SSH_KEY` | the **private** SSH key (full text, including the `BEGIN/END` lines) |
| `DO_DEPLOY_DIR` | `/opt/ask-territory` |

That's it. Push to `main` (or run the **Deploy to DigitalOcean** workflow
manually from the Actions tab) and it deploys.

## Step 4 — Domain + HTTPS (optional, reuse your existing setup)

You already had Cloudflare in front of the Oracle box — keep it. In Cloudflare
→ DNS, edit the existing **A record** to point at the new droplet IP. Set
SSL/TLS mode to **Full**. Cloudflare terminates HTTPS; nginx serves plain HTTP
on the origin, so nothing else changes.

(If you'd rather use Let's Encrypt directly on the droplet instead of
Cloudflare: `sudo apt install certbot python3-certbot-nginx && sudo certbot
--nginx -d yourdomain.com` after pointing DNS at the droplet.)

---

## Later: turn on the self-hosted AI model

The model (Ollama + Qwen2.5) needs real RAM. On CPU, give it **8 GB+**
(~$48/mo droplet); a GPU droplet is faster but much pricier.

1. Resize the droplet (Power off → Resize → 8 GB) or create a bigger one.
2. On the droplet:
   ```bash
   cd /opt/ask-territory
   sudo docker compose --profile model up -d --build      # starts web + ollama + refresh
   sudo docker compose exec ollama ollama pull qwen2.5:7b-instruct
   ```
3. The chat in the **Ask AI** page comes online automatically once
   `/api/health` reports `model_server: true`.

To make CI deploys keep the model running, change the deploy step in
`.github/workflows/deploy.yml` from `docker compose up -d --build` to
`docker compose --profile model up -d --build`.

---

## Troubleshooting

- **Deploy job fails at "Set up SSH" / can't connect** → check `DO_HOST` is the
  right IP, `DO_USER` matches, and `DO_SSH_KEY` is the *private* key whose public
  half is in the droplet's `~/.ssh/authorized_keys`.
- **Site 502 in browser** → the web container isn't up. `ssh` in and run
  `sudo docker compose ps` and `sudo docker compose logs web`.
- **Chat says "model offline"** → expected on the web-only droplet. See the
  section above to enable the model.
