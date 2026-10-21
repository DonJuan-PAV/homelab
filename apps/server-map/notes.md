# Router (Fizz)
- Admin page: `http://192.168.0.1`
- Port forwarding: TCP **80** and **443** → the Ubuntu server (for Caddy). Nothing else.
- DHCP reservation keeps the server's home IP from changing
- UPnP: off

# Domain
- `ricamivida.com` registered at GoDaddy
- A record `movies` → home public IP (update it if the "Heads up" box says the IP changed)

# Caddy
- Folder: `~/caddy` (Caddyfile + docker-compose.yml)
- `default_bind` is set to the server's home IP so it doesn't clash with Tailscale on port 443
- To add a new public app: add a block to the Caddyfile, add an A record at GoDaddy, then `docker compose restart`

# Private only (never expose through Caddy)
- Portainer, qBittorrent, Vaultwarden, Pi-hole, Home Base, File Browser, this map
- Vaultwarden is reached through Tailscale at the server's .ts.net address

# Jellyfin
- Media folder is mounted read-only
- Admin account: home/Tailscale only, hidden from login screen
- Has its own DNS (1.1.1.1 / 8.8.8.8) in docker-compose.yml so metadata lookups work

# Backups
- restic in `~/backup-system`, runs nightly from root's crontab
- Copies to the USB key and an encrypted Google Drive copy
- Movies/shows are not backed up

# Never write passwords in this file
