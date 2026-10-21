#!/usr/bin/env python3
"""
Server Map
----------
Reads live information from this server (Docker containers, ports, folders,
IP addresses, public domains, scheduled tasks) and writes one HTML page:
    ~/server-map/output/index.html

Run it by hand any time:   python3 ~/server-map/generate.py
It is also meant to run automatically from cron (see README).

Only uses Python's standard library, so nothing needs to be installed.
"""

import datetime
import html
import json
import os
import re
import shutil
import socket
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output" / "index.html"
NOTES = HERE / "notes.md"
CADDYFILE = Path(os.environ.get("CADDYFILE", str(Path.home() / "caddy" / "Caddyfile")))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def run(cmd, timeout=15):
    """Run a command and return its output, or "" if it fails."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def e(value):
    """Escape text so it is safe to put inside HTML."""
    return html.escape(str(value), quote=True)


# --------------------------------------------------------------------------
# Collect information
# --------------------------------------------------------------------------

def docker_containers():
    ids = run(["docker", "ps", "-aq"]).split()
    if not ids:
        return []
    try:
        items = json.loads(run(["docker", "inspect", *ids], timeout=30) or "[]")
    except json.JSONDecodeError:
        return []

    id_to_name = {c.get("Id", ""): c.get("Name", "").lstrip("/") for c in items}
    out = []
    for c in items:
        cfg = c.get("Config") or {}
        hc = c.get("HostConfig") or {}
        ns = c.get("NetworkSettings") or {}
        st = c.get("State") or {}
        labels = cfg.get("Labels") or {}

        ports, seen = [], {}
        for cport, binds in (ns.get("Ports") or {}).items():
            for b in binds or []:
                key = (b.get("HostPort"), cport)
                local = b.get("HostIp", "").startswith("127.") or b.get("HostIp") == "::1"
                if key in seen:
                    # if any binding is public, the port is public
                    seen[key]["local_only"] = seen[key]["local_only"] and local
                    continue
                p = {"host": int(b["HostPort"]), "container": cport, "local_only": local}
                seen[key] = p
                ports.append(p)
        ports.sort(key=lambda p: p["host"])

        netmode = hc.get("NetworkMode", "") or ""
        if netmode.startswith("container:"):
            target = netmode.split(":", 1)[1]
            for cid, name in id_to_name.items():
                if cid.startswith(target) or name == target:
                    netmode = "container:" + name
                    break

        mounts = [
            {
                "src": m.get("Source", "") if m.get("Type") == "bind" else "volume: " + (m.get("Name") or ""),
                "dst": m.get("Destination", ""),
                "rw": m.get("RW", True),
            }
            for m in c.get("Mounts") or []
        ]

        out.append({
            "name": c.get("Name", "").lstrip("/"),
            "image": cfg.get("Image", ""),
            "running": st.get("Running", False),
            "status": st.get("Status", ""),
            "restart": (hc.get("RestartPolicy") or {}).get("Name", "") or "no",
            "netmode": netmode,
            "ports": ports,
            "mounts": mounts,
            "folder": labels.get("com.docker.compose.project.working_dir", ""),
            "compose": labels.get("com.docker.compose.project.config_files", ""),
        })

    # Apps sharing another container's network (e.g. qBittorrent behind Gluetun)
    by_name = {c["name"]: c for c in out}
    for c in out:
        if c["netmode"].startswith("container:"):
            parent = by_name.get(c["netmode"].split(":", 1)[1])
            if parent:
                parent.setdefault("guests", []).append(c["name"])

    # Caddy (or anything) on host networking: show the web ports it serves
    for c in out:
        if c["netmode"] == "host" and "caddy" in c["name"].lower():
            c["ports"] = [
                {"host": 80, "container": "80/tcp", "local_only": False},
                {"host": 443, "container": "443/tcp", "local_only": False},
            ]

    out.sort(key=lambda c: c["name"].lower())
    return out


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 80))  # no data is sent; this just picks the right network card
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def tailscale_info():
    ips = run(["tailscale", "ip", "-4"]).split()
    dns_name = ""
    try:
        dns_name = json.loads(run(["tailscale", "status", "--json"]) or "{}")["Self"]["DNSName"].rstrip(".")
    except (KeyError, TypeError, json.JSONDecodeError):
        pass
    return (ips[0] if ips else ""), dns_name


def public_ip():
    for url in ("https://ifconfig.me/ip", "https://api.ipify.org"):
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                ip = r.read().decode().strip()
                if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
                    return ip
        except Exception:
            continue
    return ""


def resolve(domain):
    try:
        return socket.gethostbyname(domain)
    except OSError:
        return ""


def caddy_sites():
    """Find 'domain { reverse_proxy host:port }' blocks in the Caddyfile."""
    try:
        text = CADDYFILE.read_text()
    except OSError:
        return []
    sites, depth, current = [], 0, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if depth == 0 and line.endswith("{") and line != "{":
            names = line[:-1].replace(",", " ").split()
            current = {"domains": names, "upstreams": []}
            sites.append(current)
        elif depth >= 1 and current is not None:
            m = re.match(r"reverse_proxy\s+(.+?)\s*\{?$", line)
            if m:
                current["upstreams"] += [u for u in m.group(1).split() if u != "{"]
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            depth, current = 0, None
    return sites


def system_info():
    info = {"hostname": socket.gethostname(), "os": "", "uptime": "", "disk": None, "mem": ""}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                info["os"] = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    try:
        secs = int(float(Path("/proc/uptime").read_text().split()[0]))
        d, h, m = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
        info["uptime"] = f"{d}d {h}h {m}m"
    except (OSError, ValueError, IndexError):
        pass
    try:
        info["disk"] = shutil.disk_usage("/")
    except OSError:
        pass
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0])
        used = (mem["MemTotal"] - mem["MemAvailable"]) / 1048576
        info["mem"] = f"{used:.1f} / {mem['MemTotal'] / 1048576:.1f} GB"
    except (OSError, KeyError, ValueError):
        pass
    return info


def cron_jobs():
    jobs = []
    for line in run(["crontab", "-l"]).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            jobs.append(line)
    return jobs


# --------------------------------------------------------------------------
# Tiny Markdown → HTML for notes.md (headings, bullets, `code`, **bold**)
# --------------------------------------------------------------------------

def inline_md(text):
    text = e(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def notes_html():
    try:
        lines = NOTES.read_text().splitlines()
    except OSError:
        return "<p class='muted'>No notes.md yet.</p>"
    out, in_list = [], False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline_md(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("#"):
            out.append(f"<h3>{inline_md(line.lstrip('#').strip())}</h3>")
        elif line.strip():
            out.append(f"<p>{inline_md(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Build the page
# --------------------------------------------------------------------------

def gb(n):
    return f"{n / 1e9:.0f} GB"


def build():
    containers = docker_containers()
    lan = lan_ip()
    ts_ip, ts_name = tailscale_info()
    pub = public_ip()
    sites = caddy_sites()
    sysinfo = system_info()
    jobs = cron_jobs()
    now = datetime.datetime.now().astimezone()

    port_owner = {}
    for c in containers:
        for p in c["ports"]:
            port_owner.setdefault(p["host"], c["name"])

    # domain → app
    domain_rows, app_domains, warnings = [], {}, []
    for s in sites:
        for d in s["domains"]:
            ups = s["upstreams"]
            app = ""
            for u in ups:
                m = re.search(r":(\d+)$", u)
                if m and int(m.group(1)) in port_owner:
                    app = port_owner[int(m.group(1))]
            if app:
                app_domains.setdefault(app, []).append(d)
            ip = resolve(d)
            ok = bool(ip and pub and ip == pub)
            if pub and ip and ip != pub:
                warnings.append(
                    f"<strong>{e(d)}</strong> points to {e(ip)}, but your home's public IP is now "
                    f"{e(pub)}. Update the A record at GoDaddy."
                )
            domain_rows.append((d, ups, app, ip, ok))

    for c in containers:
        if not c["running"]:
            warnings.append(f"<strong>{e(c['name'])}</strong> is not running ({e(c['status'])}).")
        if c["restart"] == "no":
            warnings.append(
                f"<strong>{e(c['name'])}</strong> has no restart policy, so it won't come back after a reboot."
            )

    running = sum(1 for c in containers if c["running"])

    # ---------- overview tiles ----------
    disk = sysinfo["disk"]
    disk_txt = f"{gb(disk.used)} / {gb(disk.total)}" if disk else "?"
    disk_pct = int(disk.used / disk.total * 100) if disk else 0
    tiles = [
        ("Machine", sysinfo["hostname"], sysinfo["os"]),
        ("Home IP", lan or "?", "inside your home network"),
        ("Tailscale", ts_ip or "not running", ts_name or "private, from anywhere"),
        ("Public IP", pub or "?", "what the internet sees"),
        ("Containers", f"{running} / {len(containers)}", "running / total"),
        ("Disk", disk_txt, f"{disk_pct}% used"),
        ("Memory", sysinfo["mem"] or "?", "used / total"),
        ("Uptime", sysinfo["uptime"] or "?", "since last reboot"),
    ]
    tiles_html = "".join(
        f"<div class='tile'><span class='label'>{e(a)}</span>"
        f"<span class='value'>{e(b)}</span><span class='sub'>{e(c)}</span></div>"
        for a, b, c in tiles
    )

    # ---------- apps table ----------
    app_rows = []
    for c in containers:
        links, port_chips = [], []
        for p in c["ports"]:
            badge = " <span class='badge'>server only</span>" if p["local_only"] else ""
            port_chips.append(f"<span class='chip'>{p['host']} → {e(p['container'])}</span>{badge}")
            if not p["local_only"] and p["host"] not in (53, 443) and lan and "/udp" not in p["container"]:
                links.append(f"<a href='http://{e(lan)}:{p['host']}' target='_blank'>home</a>")
                if ts_ip:
                    links.append(f"<a href='http://{e(ts_ip)}:{p['host']}' target='_blank'>tailscale</a>")
        for d in app_domains.get(c["name"], []):
            links.insert(0, f"<a class='public' href='https://{e(d)}' target='_blank'>{e(d)}</a>")
        if c["netmode"].startswith("container:"):
            port_chips.append(f"<span class='badge'>uses {e(c['netmode'].split(':', 1)[1])}'s network</span>")
        elif c["netmode"] == "host":
            port_chips.append("<span class='badge'>host network</span>")
        if c.get("guests"):
            port_chips.append(f"<span class='badge'>also serves {e(', '.join(c['guests']))}</span>")

        dot = "on" if c["running"] else "off"
        search = " ".join([c["name"], c["image"], c["folder"], *[str(p["host"]) for p in c["ports"]],
                           *app_domains.get(c["name"], [])]).lower()
        app_rows.append(
            f"<tr data-search='{e(search)}'>"
            f"<td><span class='dot {dot}'></span><strong>{e(c['name'])}</strong>"
            f"<div class='sub'>{e(c['image'])}</div></td>"
            f"<td>{'<br>'.join(port_chips) or '<span class=muted>none</span>'}</td>"
            f"<td class='links'>{' · '.join(links) or '<span class=muted>—</span>'}</td>"
            f"<td><code>{e(c['folder'] or '—')}</code></td>"
            f"<td>{e(c['restart'])}</td></tr>"
        )

    # ---------- port index ----------
    port_rows = []
    for c in containers:
        for p in c["ports"]:
            where = "server only" if p["local_only"] else "home + tailscale"
            if p["host"] in (80, 443) and "caddy" in c["name"].lower():
                where = "public (router forwards it)"
            port_rows.append((p["host"], p["container"], c["name"], where))
    port_rows.sort()
    port_html = "".join(
        f"<tr data-search='{h} {e(n).lower()}'><td><strong>{h}</strong></td>"
        f"<td>{e(cp)}</td><td>{e(n)}</td><td>{e(w)}</td></tr>"
        for h, cp, n, w in port_rows
    )

    # ---------- domains ----------
    dom_html = "".join(
        f"<tr data-search='{e(d).lower()} {e(a).lower()}'>"
        f"<td><a class='public' href='https://{e(d)}' target='_blank'>{e(d)}</a></td>"
        f"<td><code>{e(', '.join(u))}</code></td><td>{e(a or '?')}</td>"
        f"<td>{e(ip or 'not found')} {'<span class=ok>✓ matches</span>' if ok else ''}</td></tr>"
        for d, u, a, ip, ok in domain_rows
    ) or "<tr><td colspan='4' class='muted'>No Caddyfile found.</td></tr>"

    # ---------- storage ----------
    storage_html = ""
    for c in containers:
        if not c["mounts"]:
            continue
        rows = "".join(
            f"<li><code>{e(m['src'])}</code> → <code>{e(m['dst'])}</code>"
            f"{'' if m['rw'] else ' <span class=badge>read-only</span>'}</li>"
            for m in c["mounts"]
        )
        compose = f"<div class='sub'>settings file: <code>{e(c['compose'])}</code></div>" if c["compose"] else ""
        storage_html += (
            f"<details data-search='{e(c['name']).lower()} "
            f"{e(' '.join(m['src'] for m in c['mounts'])).lower()}'>"
            f"<summary>{e(c['name'])}</summary>{compose}<ul>{rows}</ul></details>"
        )

    cron_html = "".join(f"<li><code>{e(j)}</code></li>" for j in jobs) or \
        "<li class='muted'>No jobs in your user crontab (root's jobs, like backups, aren't listed here).</li>"

    warn_html = ""
    if warnings:
        warn_html = "<section class='warn'><h2>Heads up</h2><ul>" + \
            "".join(f"<li>{w}</li>" for w in warnings) + "</ul></section>"

    page = TEMPLATE.format(
        host=e(sysinfo["hostname"]),
        updated=e(now.strftime("%a %b %d, %Y · %H:%M")),
        tiles=tiles_html,
        warnings=warn_html,
        apps="".join(app_rows) or "<tr><td colspan='5' class='muted'>Docker not reachable.</td></tr>",
        ports=port_html,
        domains=dom_html,
        storage=storage_html or "<p class='muted'>No folders found.</p>",
        cron=cron_html,
        notes=notes_html(),
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    os.replace(tmp, OUTPUT)  # swap in the new page all at once
    print(f"Server map written to {OUTPUT}")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Server Map · {host}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=Unbounded:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #f1eee7; --dot: #d9d4c8; --ink: #151515; --card: #161616; --card2: #202020;
    --line: #2e2e2e; --text: #ece9e2; --muted: #8f8b83; --accent: #ff6a1a; --ok: #5fd38d;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; color: var(--ink); font: 15px/1.5 "Instrument Sans", system-ui, sans-serif;
    background-color: var(--bg);
    background-image: radial-gradient(var(--dot) 1px, transparent 1.2px);
    background-size: 14px 14px;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 16px 64px; }}
  header {{ display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 24px; }}
  h1 {{ font: 700 clamp(28px, 5vw, 44px)/1 "Unbounded", sans-serif; margin: 0; letter-spacing: -0.02em; }}
  h1 span {{ color: var(--accent); }}
  .updated {{ color: #6b675f; font-size: 13px; margin-top: 8px; }}
  input[type=search] {{
    width: min(340px, 100%); padding: 12px 16px; border-radius: 999px; border: 2px solid var(--ink);
    background: #fff; font: inherit; outline: none;
  }}
  input[type=search]:focus {{ border-color: var(--accent); }}
  .tiles {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .tile {{ background: var(--card); color: var(--text); border-radius: 18px; padding: 16px 18px; display: flex; flex-direction: column; gap: 2px; }}
  .tile .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--accent); }}
  .tile .value {{ font: 600 19px "Unbounded", sans-serif; word-break: break-all; }}
  .sub {{ color: var(--muted); font-size: 12.5px; }}
  section {{ background: var(--card); color: var(--text); border-radius: 22px; padding: 22px; margin-bottom: 20px; overflow-x: auto; }}
  h2 {{ font: 600 17px "Unbounded", sans-serif; margin: 0 0 14px; }}
  h2::before {{ content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); margin-right: 10px; }}
  table {{ width: 100%; border-collapse: collapse; min-width: 640px; }}
  th {{ text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; padding: 8px 10px; border-bottom: 1px solid var(--line); }}
  td {{ padding: 11px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  tr:last-child td {{ border-bottom: 0; }}
  code {{ font: 12.5px ui-monospace, "SF Mono", Consolas, monospace; background: var(--card2); padding: 2px 6px; border-radius: 6px; color: #f3d9c9; word-break: break-all; }}
  a {{ color: var(--text); text-decoration-color: var(--accent); text-underline-offset: 3px; }}
  a:hover {{ color: var(--accent); }}
  a.public {{ color: var(--accent); font-weight: 600; }}
  .chip {{ display: inline-block; background: var(--card2); border-radius: 8px; padding: 1px 8px; font-variant-numeric: tabular-nums; }}
  .badge {{ display: inline-block; font-size: 11px; border: 1px solid #4a4a4a; color: var(--muted); border-radius: 999px; padding: 0 8px; margin: 2px 0; }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; }}
  .dot.on {{ background: var(--ok); box-shadow: 0 0 8px var(--ok); }}
  .dot.off {{ background: #e5484d; }}
  .ok {{ color: var(--ok); font-size: 12px; margin-left: 6px; }}
  .muted {{ color: var(--muted); }}
  .warn {{ background: var(--accent); color: #1a0d05; }}
  .warn h2::before {{ background: #1a0d05; }}
  .warn code {{ background: rgba(0,0,0,.12); color: inherit; }}
  details {{ border-bottom: 1px solid var(--line); padding: 10px 0; }}
  details:last-child {{ border-bottom: 0; }}
  summary {{ cursor: pointer; font-weight: 600; }}
  summary:hover {{ color: var(--accent); }}
  details ul {{ margin: 8px 0 0; padding-left: 18px; }}
  details li {{ margin: 4px 0; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .grid2 section {{ margin-bottom: 0; }}
  .notes h3 {{ font: 600 14px "Unbounded", sans-serif; color: var(--accent); margin: 18px 0 6px; }}
  .notes h3:first-child {{ margin-top: 0; }}
  .notes ul {{ margin: 0; padding-left: 18px; }}
  footer {{ text-align: center; color: #6b675f; font-size: 13px; margin-top: 28px; }}
  .hidden {{ display: none !important; }}
  @media (max-width: 820px) {{ .grid2 {{ grid-template-columns: 1fr; }} .grid2 section {{ margin-bottom: 20px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Server Map<span>.</span></h1>
      <div class="updated">{host} · updated {updated}</div>
    </div>
    <input type="search" id="q" placeholder="Search an app, port or folder…" autocomplete="off">
  </header>

  <div class="tiles">{tiles}</div>
  {warnings}

  <section>
    <h2>Apps</h2>
    <table class="filter">
      <thead><tr><th>App</th><th>Ports (server → app)</th><th>Open</th><th>Folder</th><th>Restart</th></tr></thead>
      <tbody>{apps}</tbody>
    </table>
  </section>

  <section>
    <h2>Public domains</h2>
    <table class="filter">
      <thead><tr><th>Address</th><th>Caddy sends it to</th><th>App</th><th>Domain points to</th></tr></thead>
      <tbody>{domains}</tbody>
    </table>
  </section>

  <div class="grid2">
    <section>
      <h2>Port index</h2>
      <table class="filter" style="min-width:0">
        <thead><tr><th>Port</th><th>Inside</th><th>App</th><th>Reachable from</th></tr></thead>
        <tbody>{ports}</tbody>
      </table>
    </section>
    <section>
      <h2>Folders &amp; storage</h2>
      <div class="filter-details">{storage}</div>
    </section>
  </div>
  <div style="height:20px"></div>

  <div class="grid2">
    <section class="notes">
      <h2>My notes</h2>
      {notes}
    </section>
    <section>
      <h2>Scheduled jobs</h2>
      <ul>{cron}</ul>
    </section>
  </div>

  <footer>Refresh now: <code style="color:#151515;background:#e4dfd4">python3 ~/server-map/generate.py</code></footer>
</div>
<script>
  const q = document.getElementById("q");
  q.addEventListener("input", () => {{
    const term = q.value.trim().toLowerCase();
    document.querySelectorAll("table.filter tbody tr, .filter-details details").forEach(el => {{
      const hay = (el.dataset.search || el.textContent).toLowerCase();
      el.classList.toggle("hidden", term !== "" && !hay.includes(term));
    }});
  }});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
