# Deploying KUHHAN on a Linux VPS (no Docker)

Target: Ubuntu 24.04 / Debian 12, a single VPS (Hostinger or similar), PostgreSQL
from the distribution, nginx in front, systemd supervising the API and the worker.

> The Base44 sandbox preview is a development environment, not a deployment. This
> document describes the production layout the repository is written for.

## 1. Packages

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential \
                    libpq-dev postgresql postgresql-client nginx git \
                    nodejs npm
sudo node -v   # needs Node 20+; use NodeSource if the distribution ships an older one
```

`postgresql-client` matters: the backup job uses `pg_dump` when available and
falls back to a logical JSON dump otherwise.

## 2. Database

```sh
sudo -u postgres psql <<'SQL'
CREATE USER kuhhan WITH PASSWORD 'change-this-strong-password';
CREATE DATABASE kuhhan OWNER kuhhan;
SQL
```

## 3. Application

```sh
sudo useradd --system --create-home --shell /usr/sbin/nologin kuhhan
sudo -u kuhhan git clone <repository-url> /opt/kuhhan
cd /opt/kuhhan/backend
sudo -u kuhhan python3 -m venv .venv
sudo -u kuhhan .venv/bin/pip install -r requirements.txt
```

Frontend build (static files served by nginx):

```sh
cd /opt/kuhhan/frontend
sudo -u kuhhan npm ci
sudo -u kuhhan npm run build        # -> /opt/kuhhan/frontend/dist
```

## 4. Environment file

Create `/etc/kuhhan/kuhhan.env` (mode `0640`, owner `kuhhan:kuhhan`):

```ini
DATABASE_URL=postgresql+psycopg://kuhhan:change-this-strong-password@localhost:5432/kuhhan
ENVIRONMENT=production
SECRET_KEY=<64+ random characters>
ENCRYPTION_KEY=<Fernet key: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<one-time bootstrap password>
CORS_ORIGINS=
ALLOW_PRIVATE_OUTBOUND=false
BACKUP_DIR=/var/backups/kuhhan
WORKER_POLL_SECONDS=15
```

`ENCRYPTION_KEY` encrypts stored third-party API credentials. Set it **before**
creating any API integration: changing it afterwards makes existing credentials
unreadable and they must be re-entered.

`CORS_ORIGINS` stays empty: nginx serves the SPA and the API from one origin.

## 5. Migrations and bootstrap

```sh
sudo -u kuhhan mkdir -p /var/backups/kuhhan
cd /opt/kuhhan/backend
sudo -u kuhhan env $(grep -v '^#' /etc/kuhhan/kuhhan.env | xargs) .venv/bin/alembic upgrade head
```

The first API start runs the idempotent bootstrap: permissions, system roles, the
administrator, default job schedules and the curated website catalogue. Change
the administrator password from the Profile screen immediately afterwards and
remove `ADMIN_PASSWORD` from the environment file.

## 6. systemd units

`/etc/systemd/system/kuhhan-api.service`:

```ini
[Unit]
Description=KUHHAN API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=kuhhan
Group=kuhhan
WorkingDirectory=/opt/kuhhan/backend
EnvironmentFile=/etc/kuhhan/kuhhan.env
ExecStart=/opt/kuhhan/backend/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/kuhhan-worker.service`:

```ini
[Unit]
Description=KUHHAN background worker
After=network.target postgresql.service kuhhan-api.service
Requires=postgresql.service

[Service]
User=kuhhan
Group=kuhhan
WorkingDirectory=/opt/kuhhan/backend
EnvironmentFile=/etc/kuhhan/kuhhan.env
ExecStart=/opt/kuhhan/backend/.venv/bin/python -m app.worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now kuhhan-api kuhhan-worker
curl -s http://127.0.0.1:8000/api/health
```

Run exactly **one** worker service: schedules are claimed from `job_schedules`, but
a single worker keeps collection pacing predictable.

## 7. nginx

`/etc/nginx/sites-available/kuhhan`:

```nginx
server {
    listen 80;
    server_name kuhhan.example.com;

    root /opt/kuhhan/frontend/dist;
    index index.html;

    client_max_body_size 2m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri /index.html;
    }
}
```

```sh
sudo ln -s /etc/nginx/sites-available/kuhhan /etc/nginx/sites-enabled/kuhhan
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d kuhhan.example.com
```

The API only listens on `127.0.0.1:8000`; nothing but nginx should reach it.

## 8. Backups

The `database_backup` job writes `pg_dump` archives into `BACKUP_DIR`, records a
checksum and never overwrites an existing archive; `retention_cleanup` prunes
them. Copy that directory off the VPS (restic, rclone or your provider's snapshot
feature) — an on-box backup does not protect against a lost VPS.

## 9. Upgrades

```sh
cd /opt/kuhhan
sudo -u kuhhan git pull
cd backend && sudo -u kuhhan .venv/bin/pip install -r requirements.txt
sudo -u kuhhan env $(grep -v '^#' /etc/kuhhan/kuhhan.env | xargs) .venv/bin/alembic upgrade head
cd ../frontend && sudo -u kuhhan npm ci && sudo -u kuhhan npm run build
sudo systemctl restart kuhhan-api kuhhan-worker
```

## 10. Security checklist

- [ ] Unique `SECRET_KEY` and `ENCRYPTION_KEY` in the environment file
- [ ] Bootstrap administrator password changed; `ADMIN_PASSWORD` removed from the file
- [ ] `ALLOW_PRIVATE_OUTBOUND=false` (keeps the SSRF guard active)
- [ ] `CORS_ORIGINS` empty (single-origin via nginx)
- [ ] PostgreSQL reachable only from localhost (`listen_addresses = 'localhost'`)
- [ ] Firewall allows 22, 80, 443 only (`ufw allow OpenSSH && ufw allow 'Nginx Full'`)
- [ ] TLS certificate installed and auto-renewing (`systemctl status certbot.timer`)
- [ ] Backups copied off the server and a restore tested once
- [ ] `/api/docs` reachable only from the admin network if the API is public-facing
