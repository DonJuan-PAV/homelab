"""
Home Base - a small homepage for a home server.
Lists the apps from apps.yaml, checks whether each one is up, and shows basic server stats.
Apps can also show live numbers on their tile (see "counts" in apps.yaml)
and an icon instead of their initials (see "icon" in apps.yaml).
"""
import json
import os
import socket
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil
import yaml
from flask import Flask, abort, jsonify, render_template, send_from_directory

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/config/apps.yaml"))
STATUS_HOST = os.environ.get("STATUS_HOST", "host.docker.internal")  # where the apps' ports live
HOST_ROOT = os.environ.get("HOST_ROOT", "/host")                     # host disk, mounted read-only
CHECK_TIMEOUT = float(os.environ.get("CHECK_TIMEOUT", 1.5))
ICONS_DIR = Path(os.environ.get("ICONS_DIR", "/config/icons"))       # your own icon files
ICON_CDN = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg"  # free app-icon library

app = Flask(__name__)
_pool = ThreadPoolExecutor(max_workers=16)


def icon_url(icon) -> str:
    """
    Turn the "icon" value from apps.yaml into an image address:
      jellyfin                      -> icon from the dashboard-icons library
      mail.svg                      -> your own file in the icons/ folder
      https://example.com/logo.png  -> used as-is
    """
    if not icon:
        return ""
    icon = str(icon).strip()
    if icon.startswith(("http://", "https://")):
        return icon
    if "." in icon:
        return f"/icons/{icon}"
    return f"{ICON_CDN}/{icon}.svg"


def load_config() -> dict:
    """Read apps.yaml on every request, so edits show up on refresh without a restart."""
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    except yaml.YAMLError as e:
        return {"title": "Home Base", "error": f"apps.yaml has a mistake: {e}", "groups": [], "clocks": []}

    groups = []
    for i, group in enumerate(data.get("groups") or []):
        apps = []
        for j, a in enumerate(group.get("apps") or []):
            if not a or not a.get("name"):
                continue
            apps.append({
                "id": f"{i}-{j}",
                "name": str(a["name"]),
                "description": str(a.get("description") or ""),
                "port": a.get("port"),
                "path": str(a.get("path") or ""),
                "scheme": str(a.get("scheme") or "http"),
                "url": a.get("url"),
                "planned": bool(a.get("planned")),
                "icon": icon_url(a.get("icon")),
                # optional live numbers: {field in the app's JSON: label on the tile}
                "counts": ({str(k): str(v) for k, v in a["counts"].items()}
                           if isinstance(a.get("counts"), dict) else {}),
            })
        if apps:
            groups.append({"name": str(group.get("name") or "Apps"), "apps": apps})

    # optional world clocks, shown top right: [{city: Amsterdam, zone: Europe/Amsterdam}]
    clocks = [{"city": str(c.get("city") or c.get("zone")), "zone": str(c["zone"])}
              for c in (data.get("clocks") or []) if isinstance(c, dict) and c.get("zone")]

    return {
        "title": str(data.get("title") or "Home Base"),
        "owner": str(data.get("owner") or ""),
        "clocks": clocks,
        "groups": groups,
        "error": None,
    }


def port_open(port: int) -> bool:
    try:
        with socket.create_connection((STATUS_HOST, int(port)), timeout=CHECK_TIMEOUT):
            return True
    except (OSError, ValueError):
        return False


@app.get("/")
def index():
    return render_template("index.html", cfg=load_config())


@app.get("/api/status")
def status():
    cfg = load_config()
    checks = {a["id"]: a["port"] for g in cfg["groups"] for a in g["apps"]
              if a["port"] and not a["planned"] and not a["url"]}
    results = dict(zip(checks, _pool.map(port_open, checks.values())))
    return jsonify({k: ("up" if v else "down") for k, v in results.items()})


def read_counts(a):
    """Ask an app for its numbers (JSON at its port + path) and keep only the listed fields."""
    url = f"http://{STATUS_HOST}:{int(a['port'])}{a['path']}"
    try:
        with urllib.request.urlopen(url, timeout=CHECK_TIMEOUT) as response:
            data = json.load(response)
    except (OSError, ValueError):
        return None  # app down or not answering JSON: the tile just shows "–"
    return {label: data.get(field) for field, label in a["counts"].items()}


@app.get("/api/counts")
def counts():
    cfg = load_config()
    apps = [a for g in cfg["groups"] for a in g["apps"]
            if a["counts"] and a["port"] and not a["planned"] and not a["url"]]
    results = _pool.map(read_counts, apps)
    return jsonify({a["id"]: r for a, r in zip(apps, results)})


@app.get("/api/stats")
def stats():
    disk_path = HOST_ROOT if os.path.isdir(HOST_ROOT) else "/"
    disk = psutil.disk_usage(disk_path)
    mem = psutil.virtual_memory()
    return jsonify({
        "cpu": psutil.cpu_percent(interval=0.3),
        "ram": mem.percent,
        "ram_used_gb": round(mem.used / 1e9, 1),
        "ram_total_gb": round(mem.total / 1e9, 1),
        "disk": disk.percent,
        "disk_free_gb": round(disk.free / 1e9),
        "uptime_s": int(time.time() - psutil.boot_time()),
    })


@app.get("/icons/<path:name>")
def icons(name):
    """Serve your own icon files from the icons/ folder (no access outside it)."""
    if not ICONS_DIR.is_dir():
        abort(404)
    return send_from_directory(ICONS_DIR, name, max_age=86400)


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
