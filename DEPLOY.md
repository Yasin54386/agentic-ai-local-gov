# DEPLOY — taking Ask Territory live on your domain

This gets **Ask Territory** running publicly on the domain you bought
(`ask-territory`). Everything is self-hosted — your server, your model, your data.
No external AI API.

> **What only you can do** (needs your accounts/credentials):
> 1. Have a **server** (a VPS/cloud VM you control).
> 2. Point your **domain's DNS** at that server.
> 3. Run the deploy commands below on it.
>
> Everything else (app, model, TLS config, refresh) is automated here.

---

## Step 1 — Get a server

Any Ubuntu 22.04+ VM works. Sizing for the **7B** model on CPU:
- **Minimum:** 4 vCPU, 16 GB RAM, 40 GB disk (model replies in a few seconds–tens of seconds).
- **Better:** a GPU instance → near-instant replies (uncomment the GPU block in `docker-compose.yml`).
- **Cheapest:** run the data/UI only and use a smaller model (`qwen2.5:3b-instruct`).

Note the server's **public IP**.

---

## Step 2 — Point your domain at the server

In your domain registrar's DNS settings for **ask-territory.<your-tld>**, add:

| Type | Name | Value |
|------|------|-------|
| A | `@` | `<your server's public IP>` |
| A | `www` | `<your server's public IP>` |

Wait for it to propagate (minutes to ~an hour). Check:
```bash
dig +short ask-territory.<your-tld>     # should show your server IP
```

---

## Step 3 — Put the code on the server

```bash
ssh user@<server-ip>
sudo apt update && sudo apt install -y git
git clone <your-repo-url> /opt/ask-territory
cd /opt/ask-territory
cp .env.example .env
nano .env          # set DOMAIN=ask-territory.<your-tld> and your email
```

---

## Step 4 — Run it (Docker — recommended)

```bash
# install Docker + compose
curl -fsSL https://get.docker.com | sudo sh

# build & start: web app + local model + 6-hourly refresh
sudo docker compose up -d --build

# pull the model into Ollama (one-time, ~4.7 GB)
sudo docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

The app is now live on the server at `127.0.0.1:8000` (not yet public — nginx next).

Check it:
```bash
curl -s localhost:8000/api/health      # {"ok": true, ...}
```

---

## Step 5 — Public access + HTTPS (nginx + certbot)```bash
sudo apt install -y nginx certbot python3-certbot-nginx

# install the site config (edit the domain inside first)
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ask-territory
sudo sed -i "s/ask-territory.com.au/ask-territory.<your-tld>/g" /etc/nginx/sites-available/ask-territory
sudo ln -s /etc/nginx/sites-available/ask-territory /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# get a free TLS certificate + auto-configure HTTPS
sudo certbot --nginx -d ask-territory.<your-tld> -d www.ask-territory.<your-tld>
```

**Done.** Visit **https://ask-territory.<your-tld>** — Ask Territory is live. 🎉

certbot auto-renews the certificate. nginx forces HTTPS.

---

## Alternative — without Docker (systemd)

```bash
sudo apt install -y python3 nginx
# install Ollama + model
curl -fsSL https://ollama.com/install.sh | sudo sh
ollama pull qwen2.5:7b-instruct

# app + refresh as services
sudo useradd -m appuser && sudo chown -R appuser /opt/ask-territory
sudo cp deploy/ask-territory-web.service /etc/systemd/system/
sudo cp deploy/ask-territory-refresh.service /etc/systemd/system/
sudo cp deploy/ask-territory-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ask-territory-web
sudo systemctl enable --now ask-territory-refresh.timer
```
Then do **Step 5** (nginx + certbot) the same way.

---

## Operating it

| Task | Command (Docker) |
|------|------------------|
| Logs | `sudo docker compose logs -f web` |
| Restart | `sudo docker compose restart web` |
| Update code | `git pull && sudo docker compose up -d --build` |
| Stop | `sudo docker compose down` |
| Check refresh snapshots | `python3 -c "import sqlite3;print(sqlite3.connect('data/unified.db').execute(\"SELECT COUNT(*) FROM records WHERE dataset_id='live:darwin-weather'\").fetchone()[0])"` |

---

## Security & cost notes

- Only port 80/443 are public (nginx). The app (8000) and model (11434) stay on localhost.
- Firewall: `sudo ufw allow 80,443/tcp && sudo ufw enable`.
- Cost: just the VM. No per-query AI fees — the model is yours.
- The "Ask" tab needs the model up; all other tabs work even if the model is down.

---

## Pre-launch checklist

- [ ] DNS A records resolve to the server (`dig +short ask-territory.<your-tld>`)
- [ ] `.env` has your real `DOMAIN` and email
- [ ] `docker compose up -d` healthy (`/api/health` returns ok)
- [ ] model pulled (`ollama pull qwen2.5:7b-instruct`)
- [ ] certbot issued the certificate (HTTPS padlock shows)
- [ ] refresh running (snapshots increasing every 6h)
- [ ] Decide on the data-freshness/disclaimer wording shown to citizens
