# homelab

The setup of my home server: an Ubuntu machine running about fifteen self-hosted apps in Docker, two of them public on my own domain. Everything here is the real configuration it runs, collected automatically by [`collect.sh`](collect.sh).

## What it runs

| App | What it does | Reachable from |
|---|---|---|
| Caddy | Reverse proxy with automatic HTTPS; the only thing the internet can reach | Internet (80, 443) |
| Jellyfin | Movies and shows, streamed to any device | Internet via Caddy, home |
| [Fare Watch](https://github.com/PAV-JUAN/flight-tracker) | My flight price tracker's public website | Internet via Caddy |
| Home Base | Custom dashboard: app status, server stats, world clock, live counters | Home, Tailscale |
| Server Map | Custom page: every app, port, folder and IP, regenerated every 30 minutes | Home, Tailscale |
| Navidrome | Music library and player | Home, Tailscale |
| You Link to MP3 | Custom app: YouTube links to songs for the music library | Home, Tailscale |
| File Browser | Upload and manage media from any device | Home, Tailscale |
| mail-notifier | Custom app: counts important Outlook and Gmail emails for the dashboard | Home, Tailscale |
| Uptime Kuma | Monitors every app and the HTTPS certificates | Home, Tailscale |
| Pi-hole | Network-wide ad blocking and local DNS | DNS: home · admin: Tailscale only |
| qBittorrent + Gluetun | Torrents, forced through a NordVPN tunnel with a kill switch | Tailscale only |
| Portainer | Web UI to manage the containers | Tailscale only |
| Vaultwarden | Password manager (Bitwarden-compatible) | Tailscale only |
| Cloudflare DDNS | Keeps my domain pointed at my home IP when it changes | (no web page) |
| CrowdSec | Detects attacks in the logs and bans the attackers' IPs | (runs on the host) |

[`apps/INVENTORY.md`](apps/INVENTORY.md) lists exactly what's running, regenerated on every collect.

## How it's built

```
   Internet                                   Tailscale (my devices only)
      │ router forwards 80/443 only                       │
┌─────┼──────────────────── Ubuntu server ────────────────┼───────────┐
│  ufw firewall + CrowdSec bouncer                        │           │
│     │                                                   │           │
│   Caddy ── movies.<domain>  ──► Jellyfin          tailscale serve   │
│     │  └── flights.<domain> ──► Fare Watch        (HTTPS, .ts.net)  │
│     └─ access log ──► CrowdSec ◄── Jellyfin log         │           │
│                                                         ▼           │
│                              Portainer · qBittorrent · Pi-hole admin│
│                              Vaultwarden  (listen on 127.0.0.1 only)│
│                                                                     │
│  Home Base · Server Map · Uptime Kuma · Navidrome · File Browser    │
│  Jellyfin ─┬─ shared media folder ◄── qBittorrent ── Gluetun ── VPN │
│  Navidrome ◄── You Link to MP3                                      │
│  mail-notifier ── Outlook (Graph API) + Gmail (IMAP)                │
│  Cloudflare DDNS ── updates the domain's IP every 5 minutes         │
└─────────────────────────────────────────────────────────────────────┘
```

## Security: defense in depth

Every layer assumes the one in front of it might fail.

1. **Router.** Only ports 80 and 443 are forwarded, both to Caddy. UPnP is off, so no app can open a port by itself.
2. **Host firewall (ufw).** Incoming traffic is denied by default. SSH is allowed only from the home network, Tailscale is allowed in full, and Caddy's two ports are open. The exported rules are in [`security/ufw-rules.txt`](security/ufw-rules.txt).
3. **Docker goes around ufw, so ports are bound on purpose.** Docker publishes container ports with its own firewall rules, which skip ufw entirely. So the admin tools (Portainer, qBittorrent, Pi-hole's admin page, Vaultwarden) are published on `127.0.0.1` only, where no other device can reach them, and `tailscale serve` forwards to them with HTTPS on the server's private `.ts.net` address. Only my own Tailscale devices can open them.
4. **CrowdSec.** It reads Caddy's access log and Jellyfin's log, detects scans, web attacks and password guessing, and its firewall bouncer bans those IPs. It also applies CrowdSec's community blocklist of known attackers. Caddy runs on the host network, so it sees real visitor IPs, and bans happen before traffic reaches any app. Log sources are in [`security/crowdsec/`](security/crowdsec/).
5. **Apps hardened individually.** Jellyfin's media folder is mounted read-only, its admin account can't log in remotely, and accounts lock after repeated failed logins. Fare Watch reads the database through a user that can only `SELECT`.

## Problems I hit and how I fixed them

- **Caddy and Tailscale both wanted port 443.** Tailscale already serves HTTPS on its own IP, so Caddy uses `default_bind` to listen only on the home network address.
- **The public sites timed out from inside the house.** The router can't loop traffic back to its own public IP (no NAT loopback). Pi-hole now answers the domains with the server's local address for devices at home, and Uptime Kuma gets the same through `extra_hosts`.
- **Jellyfin saw every visitor as Docker's gateway IP**, so brute-force protection couldn't tell attackers apart. Adding the gateway as a known proxy lets Jellyfin trust Caddy's `X-Forwarded-For` header and log the real IP.
- **CrowdSec's API defaults to port 8080**, already used by You Link to MP3, so it was moved to 8180.
- **Jellyfin couldn't fetch movie metadata.** The container couldn't resolve DNS with the host's setup, so it has its own `dns:` servers in its compose file.
- **qBittorrent rejected links from the dashboard.** Its CSRF protection blocked requests carrying another site's `Referer`, so Home Base sends no referrer instead of turning that protection off.
- **Uptime Kuma couldn't check apps that listen on `127.0.0.1`** from inside its container, so it runs on the host network, with ufw rules for who can reach its page.
- **The home IP can change.** The domain's DNS is on Cloudflare, and a small container updates the record within 5 minutes of a change.

## Other decisions

- **VPN only where it's needed.** qBittorrent has no network of its own (`network_mode: service:gluetun`), so all of its traffic goes through the VPN, and if the tunnel drops it loses internet instead of leaking the home IP.
- **Secrets never live in compose files.** Each app reads them from its own `.env`, which is git-ignored; this repo only contains `.env.example` files with the names.
- **Read-only where possible.** The dashboard mounts the host disk read-only, and config files are mounted read-only.
- **Health-aware startup.** qBittorrent waits until the VPN container reports healthy before starting.
- **Backups.** Nightly restic backups to a USB drive plus an encrypted off-site copy on Google Drive, with a restore test.

## Layout

```
apps/<app>/          docker-compose.yml, Dockerfile and config for each app
apps/INVENTORY.md    what's running, generated
security/            ufw rules and CrowdSec log sources, exported from the host
collect.sh           gathers everything above from the live server
```

## Updating this repo

```bash
./collect.sh          # copies the current setup, writes .env.example files, exports security settings, scans for secrets
git diff              # review what changed
git add -A && git commit -m "Describe the change" && git push
```

`collect.sh` stops with an error if it finds a password written in plain text, so it can't be committed by accident.

## Rebuilding the server from this repo

1. Install Ubuntu Server, Docker and Docker Compose.
2. Clone this repo, and for each app: copy `.env.example` to `.env` and fill in the values.
3. Restore the media and app data from backup.
4. In each `apps/<app>/` folder: `docker compose up -d`.
5. Recreate the firewall rules from `security/ufw-rules.txt`, install CrowdSec with its firewall bouncer, and copy the files from `security/crowdsec/acquis.d/` to `/etc/crowdsec/acquis.d/`.
