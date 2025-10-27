from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="DisTask Landing", docs_url=None, redoc_url=None)

HTML = """<!DOCTYPE html>
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
            --bg-base: #1a0b2e;
            --gradient-start: #667eea;
            --gradient-end: #764ba2;
            --text-primary: hsl(0 0% 98%);
            --text-muted: hsl(240 5% 64.9%);
            --card-bg: hsla(240, 3.7%, 15.9%, 0.85);
            --border-color: rgba(255, 255, 255, 0.08);
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
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        main {
            width: 100%;
            max-width: 960px;
            padding: 2rem;
            position: relative;
            text-align: center;
            z-index: 2;
        }
        .hero-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 32px;
            padding: 3rem;
            backdrop-filter: blur(12px);
            box-shadow: 0 20px 80px rgba(0, 0, 0, 0.6);
            animation: fade-in-up 1s ease forwards;
        }
        h1 {
            font-size: clamp(2.5rem, 5vw, 4rem);
            margin: 0 0 1rem;
            font-weight: 800;
            background: linear-gradient(120deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gradient-shift 6s ease-in-out infinite;
            background-size: 200% 200%;
        }
        p.lede {
            font-size: 1.125rem;
            color: var(--text-muted);
            margin-bottom: 2rem;
            line-height: 1.6;
        }
        .cta-group {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            justify-content: center;
            margin-bottom: 2.5rem;
        }
        .btn {
            padding: 0.85rem 1.75rem;
            border-radius: 999px;
            border: 1px solid transparent;
            text-decoration: none;
            font-weight: 600;
            font-size: 1rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .btn-primary {
            background: linear-gradient(120deg, var(--gradient-start), var(--gradient-end));
            color: white;
            box-shadow: 0 20px 40px rgba(102, 126, 234, 0.35);
        }
        .btn-secondary {
            background: transparent;
            border-color: rgba(255, 255, 255, 0.2);
            color: var(--text-primary);
        }
        .btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 30px 60px rgba(102, 126, 234, 0.45);
        }
        .btn:active {
            transform: scale(0.96);
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.15);
            padding: 0.35rem 1rem;
            background: rgba(255,255,255,0.05);
            font-size: 0.9rem;
            font-weight: 500;
            margin: 0 auto 1.5rem;
        }
        .status-dot {
            width: 0.65rem;
            height: 0.65rem;
            border-radius: 50%;
            background: var(--status-up);
            box-shadow: 0 0 12px rgba(0,0,0,0.4);
        }
        .status-desc {
            font-size: 0.95rem;
            color: var(--text-muted);
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-top: 2rem;
        }
        .feature-card {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 24px;
            padding: 1.5rem;
            text-align: left;
            min-height: 160px;
            animation: fade-in-up 1s ease forwards;
        }
        .feature-card:nth-child(2) { animation-delay: 0.15s; }
        .feature-card:nth-child(3) { animation-delay: 0.3s; }
        .feature-card:nth-child(4) { animation-delay: 0.45s; }
        .feature-card h3 {
            margin: 0 0 0.5rem;
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
        }
        .feature-card p {
            margin: 0;
            color: var(--text-muted);
            line-height: 1.5;
        }
        footer {
            margin-top: 2.5rem;
            font-size: 0.9rem;
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
        @keyframes fade-in-up {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @media (max-width: 640px) {
            body { padding: 1rem; }
            .hero-card { padding: 2rem; }
            .cta-group { flex-direction: column; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; }
        }
    </style>
</head>
<body>
    <div id=\"particles-js\"></div>
    <main>
        <section class=\"hero-card\">
            <div class=\"status-pill\" id=\"status-pill\">
                <span class=\"status-dot\" id=\"status-dot\"></span>
                <span class=\"status-label\" id=\"status-label\">Checking Status…</span>
            </div>
            <h1>DisTask</h1>
            <p class=\"lede\">Orchestrate disciplined Discord workflows with kanban clarity, slash-command speed, and reliable reminders that keep every guild project humming.</p>
            <p class=\"status-desc\" id=\"status-desc\">Connecting to bot service…</p>
            <div class=\"cta-group\">
                <a class=\"btn btn-primary\" href=\"https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands\" target=\"_blank\" rel=\"noopener\">
                    <i data-lucide=\"zap\" class=\"icon\"></i>
                    Deploy to Discord
                </a>
                <a class=\"btn btn-secondary\" href=\"https://github.com/NYTEMODEONLY/distask\" target=\"_blank\" rel=\"noopener\">
                    <i data-lucide=\"book\" class=\"icon\"></i>
                    Explore Docs
                </a>
            </div>
            <div class=\"feature-grid\">
                <div class=\"feature-card\">
                    <h3>Automated Boards</h3>
                    <p>Spin up kanban boards, columns, and precision task flows fully inside Discord with slash-first ergonomics.</p>
                </div>
                <div class=\"feature-card\">
                    <h3>Smart Reminders</h3>
                    <p>Timezone-friendly digest alerts track overdue work and upcoming deadlines without drowning chats.</p>
                </div>
                <div class=\"feature-card\">
                    <h3>Rich Permissions</h3>
                    <p>Respect server roles by gating admin, notification and board management commands with intent.</p>
                </div>
                <div class=\"feature-card\">
                    <h3>Open & Extensible</h3>
                    <p>MIT-licensed core, async API, and thoughtful utility modules ready for your next workflow idea.</p>
                </div>
            </div>
            <footer>
                <span>Built by <a class=\"link\" href=\"https://nytemode.com\" target=\"_blank\" rel=\"noopener\">nytemode</a> · Status pulses every 10 seconds</span>
            </footer>
        </section>
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
