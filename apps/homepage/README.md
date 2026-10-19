# Home Base

A homepage for your home server: one place with a tile for every app, whether each app is running, and live CPU, memory and disk meters.

## Start it

On the server, inside this folder:

```bash
docker compose up -d --build
```

Then open `http://SERVER-IP` (no port number). It also works over Tailscale: `http://100.x.x.x`.

If the page doesn't load, the firewall may be blocking port 80: `sudo ufw allow 80`.

## Add or change an app

Everything is in `apps.yaml`. Edit it (WinSCP can open it directly), save, and refresh the page. No restart needed.

A running app:

```yaml
      - name: Jellyfin
        description: Movies and shows, streamed like Netflix
        port: 8096
```

An app you plan to install later shows greyed out under "Coming next":

```yaml
        planned: true
```

When you install it, delete the `planned: true` line (and move it to another group if you like).

Other options: `scheme: https` for apps that use https (like Portainer), `path: /admin` to open a specific page, and `url: https://…` for websites outside the server.

## How it works

- Links are built from the address you used to open the page, so the same tiles work at home (`192.168.x.x`) and away (Tailscale `100.x.x.x`).
- "Running" means the app's port answers on the server. It refreshes every 30 seconds.
- Meters refresh every 5 seconds. Disk shows free space on the server's main drive (mounted read-only).

## Troubleshooting

**Every app says "Not responding" but they work:** the firewall is blocking Docker from reaching the server's ports. Allow Docker's internal networks:

```bash
sudo ufw allow from 172.16.0.0/12
```

**"apps.yaml has a mistake":** usually indentation. YAML needs spaces (not tabs), lined up exactly like the examples.
