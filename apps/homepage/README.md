# homelab

The setup of my home server: an Ubuntu machine running about fifteen self-hosted apps in Docker. Everything here is the real configuration it runs, collected automatically by [`collect.sh`](collect.sh).

## What it runs

| App | What it does | Port |
|---|---|---|
| Caddy | Reverse proxy with automatic HTTPS; the only thing the internet can reach | 80, 443 |
| Home Base | Custom dashboard: app status, server stats, world clock, live counters | 8088 |
| Server Map | Custom page: every app, port, folder and IP, regenerated every 30 min | 8099 |
| Jellyfin | Movies and shows, streamed to any device (public at `movies.` via Caddy) | 8096 |
| Navidrome | Music library and player | 4533 |
| You Link to MP3 | Custom app: YouTube links to songs for the music library | 8080 |
| File Browser | Upload and manage media from any device | 8085 |
| qBittorrent + Gluetun | Torrents, forced through a NordVPN tunnel with a kill switch | 8070 |
| mail-notifier | Custom app: counts important Outlook and Gmail emails for the dashboard | 8090 |
| Pi-hole | Network-wide ad blocking (DNS) | 8053 |
| Portainer | Web UI to manage the containers | 9443 |
| Vaultwarden | Password manager (Bitwarden-compatible), Tailscale only | 8222 |
| Uptime Kuma | Monitors every app and the HTTPS certificate | 3001 |

Only **Jellyfin** is public, behind Caddy at `movies.<my-domain>` with a Let's Encrypt certificate. Everything else stays private and is reached from outside through **Tailscale**. [`apps/INVENTORY.md`](apps/INVENTORY.md) lists exactly what's running, regenerated on every collect.

## How it's built

```
   Internet (HTTPS)                     Tailscale (private remote access)
        │ router forwards 80/443 only            │
┌───────┼─────────────── Ubuntu server ──────────┼────────────┐
│     Caddy ── movies.<domain> ──► Jellyfin       └─► all apps │
│  Home Base ── checks every app's port, shows live numbers   │
│                                                             │
│  Jellyfin ─┐                                                │
│  File Browser ─┼── shared media folder ◄── qBittorrent      │
│  Navidrome ◄─── You Link to MP3            │                │
│                                           Gluetun ── NordVPN│
│  mail-notifier ── Outlook (Graph API) + Gmail (IMAP)        │
│  Pi-hole (DNS)   Portainer   Vaultwarden   Uptime Kuma      │
│  Server Map ── reads Docker, Tailscale, Caddyfile ── page   │
└─────────────────────────────────────────────────────────────┘
```

A few decisions worth noting:

- **One door to the internet.** The router forwards only ports 80 and 443, both to Caddy, which serves only the domains listed in its Caddyfile. Admin tools (Portainer, qBittorrent, Vaultwarden, Pi-hole) are never routed through it.
- **Caddy shares port 443 with Tailscale.** Tailscale already serves HTTPS on its own IP, so Caddy uses `default_bind` to listen only on the home network address instead of every address.
- **Jellyfin hardening.** The media folder is mounted read-only, the admin account can't log in remotely and is hidden from the login screen, and accounts lock after repeated failed logins.
- **Per-container DNS where Pi-hole gets in the way.** Jellyfin couldn't resolve metadata servers with the host's DNS setup, so it has its own `dns:` servers in its compose file.
- **No referrer from the dashboard.** Home Base sends no `Referer` header, so apps with CSRF protection (like qBittorrent) accept links from its tiles without turning that protection off.

- **VPN only where it's needed.** qBittorrent has no network of its own (`network_mode: service:gluetun`), so all of its traffic goes through the VPN, and if the tunnel drops it loses internet instead of leaking the home IP. Every other app keeps the normal connection.
- **Secrets never live in compose files.** Each app reads them from its own `.env`, which is git-ignored; this repo only contains `.env.example` files with the names.
- **Read-only where possible.** The dashboard mounts the host disk read-only (for the free-space meter) and the config files read-only.
- **Health-aware startup.** qBittorrent waits until the VPN container reports healthy before starting.

## Layout

```
apps/<app>/          docker-compose.yml, Dockerfile and config for each app
apps/INVENTORY.md    what's running, generated
collect.sh           gathers everything above from the live server
```

## Updating this repo

```bash
./collect.sh          # copies the current setup, writes .env.example files, scans for secrets
git diff              # review what changed
git add . && git commit -m "Describe the change" && git push
```

`collect.sh` stops with an error if it finds a password written in plain text, so it can't be committed by accident.

## Rebuilding the server from this repo

1. Install Ubuntu Server, Docker and Docker Compose.
2. Clone this repo, and for each app: copy `.env.example` to `.env` and fill in the values.
3. Restore the media and app data from backup.
4. In each `apps/<app>/` folder: `docker compose up -d`.
