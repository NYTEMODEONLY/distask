from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="DisTask Landing", docs_url=None, redoc_url=None)

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1432225946219450449")
INVITE_URL = os.getenv("DISCORD_INVITE_URL") or f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot%20applications.commands"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>DisTask · Discord Workflows</title>
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
    <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap\" rel=\"stylesheet\" />
    <script src=\"https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js\" defer></script>
    <script src=\"https://unpkg.com/lucide@latest/dist/umd/lucide.min.js\" defer></script>
    <style>
        :root {
            --bg-base: #0f051b;
            --bg-highlight: radial-gradient(circle at 30% 20%, rgba(118,75,162,0.45), transparent 50%),
                             radial-gradient(circle at 70% 80%, rgba(102,126,234,0.35), transparent 45%);
            --text-primary: hsl(0 0% 98%);
            --text-muted: hsl(240 5% 75%);
            --gradient-start: #667eea;
            --gradient-end: #764ba2;
            --status-up: #3ddab4;
            --status-down: #ff5c7a;
            --status-degraded: #f6c177;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-base);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
        }
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background: var(--bg-highlight);
            opacity: 0.9;
            pointer-events: none;
            z-index: 0;
        }
        main {
            width: min(640px, 100%);
            text-align: center;
            z-index: 1;
        }
        h1 {
            font-size: clamp(2.25rem, 8vw, 4rem);
            margin: 0 0 1.25rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(120deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-size: 200% 200%;
            animation: gradient-shift 6s ease-in-out infinite;
        }
        p.lede {
            font-size: 1.05rem;
            color: var(--text-muted);
            margin: 0 auto 2rem;
            line-height: 1.7;
            max-width: 48ch;
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.15);
            padding: 0.45rem 1.1rem;
            background: rgba(255,255,255,0.06);
            font-size: 0.95rem;
            font-weight: 500;
            margin-bottom: 1.5rem;
        }
        .status-dot {
            width: 0.65rem;
            height: 0.65rem;
            border-radius: 50%;
            background: var(--status-up);
            box-shadow: 0 0 16px rgba(0,0,0,0.3);
        }
        .status-desc {
            margin: 0 0 2rem;
            font-size: 0.95rem;
            color: var(--text-muted);
        }
        .cta-group {
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            margin-bottom: 2.5rem;
        }
        @media (min-width: 640px) {
            .cta-group { flex-direction: row; justify-content: center; }
        }
        .btn {
            padding: 0.85rem 1.8rem;
            border-radius: 999px;
            border: 1px solid transparent;
            text-decoration: none;
            font-weight: 600;
            font-size: 1rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            justify-content: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
            min-width: 230px;
        }
        .btn-primary {
            background: linear-gradient(120deg, var(--gradient-start), var(--gradient-end));
            color: white;
            box-shadow: 0 25px 45px rgba(118, 75, 162, 0.35);
        }
        .btn-secondary {
            background: transparent;
            border-color: rgba(255,255,255,0.25);
            color: var(--text-primary);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 30px 55px rgba(118, 75, 162, 0.45);
        }
        .btn:active { transform: scale(0.97); }
        .features {
            display: grid;
            gap: 1rem;
            margin-bottom: 2.5rem;
        }
        .feature {
            text-align: left;
            padding: 0.25rem 0;
            border-left: 2px solid rgba(255,255,255,0.15);
            padding-left: 1rem;
        }
        .feature h3 {
            margin: 0 0 0.4rem;
            font-size: 1rem;
            font-weight: 600;
        }
        .feature p {
            margin: 0;
            color: var(--text-muted);
            line-height: 1.5;
            font-size: 0.95rem;
        }
        footer {
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        a.link {
            color: var(--text-primary);
            text-decoration: none;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }
        #particles-js {
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
        }
        @keyframes gradient-shift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; }
        }
    </style>
</head>
<body>
    <div id=\"particles-js\"></div>
    <main>
        <div class=\"status-pill\" id=\"status-pill\">
            <span class=\"status-dot\" id=\"status-dot\"></span>
            <span class=\"status-label\" id=\"status-label\">Checking Status…</span>
        </div>
        <h1>DisTask</h1>
        <p class=\"lede\">Orchestrate disciplined Discord workflows with kanban clarity, slash-command speed, and reliable reminders that keep every guild project humming.</p>
        <p class=\"status-desc\" id=\"status-desc\">Connecting to bot service…</p>
        <div class=\"cta-group\">
            <a class=\"btn btn-primary\" href=\"{{INVITE_URL}}\" target=\"_blank\" rel=\"noopener\">
                <i data-lucide=\"zap\" class=\"icon\"></i>
                Deploy to Discord
            </a>
            <a class=\"btn btn-secondary\" href=\"https://github.com/NYTEMODEONLY/distask\" target=\"_blank\" rel=\"noopener\">
                <i data-lucide=\"book\" class=\"icon\"></i>
                Explore Docs
            </a>
        </div>
        <div class=\"features\">
            <div class=\"feature\">
                <h3>Automated Boards</h3>
                <p>Spin up kanban boards, columns, and precision task flows inside Discord.</p>
            </div>
            <div class=\"feature\">
                <h3>Smart Reminders</h3>
                <p>Digest alerts track overdue work and upcoming deadlines without noise.</p>
            </div>
            <div class=\"feature\">
                <h3>Rich Permissions</h3>
                <p>Respect server roles by gating board, task, and notification commands.</p>
            </div>
            <div class=\"feature\">
                <h3>Open & Extensible</h3>
                <p>MIT-licensed core with async utilities ready for your workflow ideas.</p>
            </div>
        </div>
        <footer>
            <span>Built by <a class=\"link\" href=\"https://nytemode.com\" target=\"_blank\" rel=\"noopener\">nytemode</a> · Status pulses every 10 seconds</span>
        </footer>
    </main>
    <script>
        function initParticles() {
            if (!window.particlesJS) return;
            particlesJS('particles-js', {
                particles: {
                    number: { value: 80, density: { enable: true, value_area: 800 } },
                    color: { value: '#ffffff' },
                    opacity: { value: 0.25, random: true },
                    size: { value: 3, random: true },
                    line_linked: { enable: false },
                    move: { enable: true, speed: 0.8, direction: 'none', out_mode: 'out' }
                },
                interactivity: { detect_on: 'canvas', events: { onhover: { enable: false }, onclick: { enable: false }, resize: true } },
                retina_detect: true
            });
        }
        async function refreshStatus() {
            const dot = document.getElementById('status-dot');
            const label = document.getElementById('status-label');
            const desc = document.getElementById('status-desc');
            try {
                const res = await fetch(`/status?ts=${Date.now()}`);
                if (!res.ok) throw new Error('Bad status');
                const data = await res.json();
                dot.style.background = data.color;
                dot.style.boxShadow = `0 0 16px ${data.color}`;
                label.textContent = data.label;
                desc.textContent = data.message;
            } catch (err) {
                dot.style.background = 'var(--status-down)';
                label.textContent = 'Status Unknown';
                desc.textContent = 'Unable to reach the monitoring service. Please retry.';
            }
        }
        document.addEventListener('DOMContentLoaded', () => {
            initParticles();
            if (window.lucide) { window.lucide.createIcons(); }
            refreshStatus();
            setInterval(refreshStatus, 10000);
        });
    </script>
</body>
</html>
"""

HTML = HTML_TEMPLATE.replace("{{INVITE_URL}}", INVITE_URL)


@app.get("/", response_class=HTMLResponse)
async def landing() -> str:
    return HTML


def _service_state(service: str = "distask.service") -> dict[str, str]:
    try:
        output = subprocess.check_output(
            [
                "systemctl",
                "show",
                service,
                "-p",
                "ActiveState",
                "-p",
                "SubState",
                "-p",
                "Result",
                "--no-page",
            ],
            text=True,
        )
    except subprocess.CalledProcessError:
        return {"ActiveState": "unknown", "SubState": "unknown", "Result": "error"}
    data: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key] = value
    return data


def _map_status(active: str, sub: str) -> tuple[str, str, str, str]:
    state = active.lower()
    if state == "active" and sub.lower() == "running":
        return ("up", "Operational", "var(--status-up)", "Bot is online and syncing slash commands.")
    if state in {"activating", "deactivating", "reloading"}:
        return (
            "degraded",
            "Degraded",
            "var(--status-degraded)",
            "Bot is transitioning states. Commands may be briefly unavailable.",
        )
    if state == "unknown":
        return (
            "unknown",
            "Unknown",
            "var(--status-degraded)",
            "Monitoring could not verify the service status.",
        )
    return ("down", "Offline", "var(--status-down)", "Bot is unreachable. Investigate the service logs.")


@app.get("/status")
async def service_status() -> JSONResponse:
    info = _service_state()
    state_key, label, color, message = _map_status(info.get("ActiveState", "unknown"), info.get("SubState", "unknown"))
    payload = {
        "state": state_key,
        "label": label,
        "color": color,
        "message": message,
        "active_state": info.get("ActiveState", "unknown"),
        "sub_state": info.get("SubState", "unknown"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(payload)
