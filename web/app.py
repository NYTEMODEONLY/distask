from __future__ import annotations

import hmac
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="DisTask Landing", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "1432225946219450449")
INVITE_URL = os.getenv("DISCORD_INVITE_URL") or f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot%20applications.commands"
SITE_ROOT = os.getenv("DISTASK_SITE_URL", "https://distask.xyz").rstrip("/")
SITE_URL = SITE_ROOT or "https://distask.xyz"
CANONICAL_URL = f"{SITE_URL}/"
PAGE_DESCRIPTION = os.getenv(
    "DISTASK_PAGE_DESCRIPTION",
    "DisTask keeps Discord projects disciplined with kanban boards, reminders, and slash-command automation in one lightweight bot.",
)
CARD_IMAGE = os.getenv(
    "DISTASK_CARD_IMAGE",
    f"{SITE_URL}/static/distask-thumb.png",
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>DisTask · Discord Workflows</title>
    <meta name=\"description\" content=\"{{DESCRIPTION}}\" />
    <meta property=\"og:type\" content=\"website\" />
    <meta property=\"og:url\" content=\"{{CANONICAL_URL}}\" />
    <meta property=\"og:title\" content=\"DisTask · Discord Workflows\" />
    <meta property=\"og:description\" content=\"{{DESCRIPTION}}\" />
    <meta property=\"og:image\" content=\"{{CARD_IMAGE}}\" />
    <meta property=\"og:image:type\" content=\"image/png\" />
    <meta property=\"og:image:width\" content=\"256\" />
    <meta property=\"og:image:height\" content=\"256\" />
    <meta name=\"twitter:card\" content=\"summary\" />
    <meta name=\"twitter:title\" content=\"DisTask · Discord Workflows\" />
    <meta name=\"twitter:description\" content=\"{{DESCRIPTION}}\" />
    <meta name=\"twitter:image\" content=\"{{CARD_IMAGE}}\" />
    <meta name=\"theme-color\" content=\"#667eea\" />
    <link rel=\"canonical\" href=\"{{CANONICAL_URL}}\" />
    <link rel=\"icon\" href=\"/static/distask-logo.png\" type=\"image/png\" />
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
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: clamp(1.6rem, 3vh, 2.8rem);
            padding: clamp(0.85rem, 3.2vw, 1.9rem);
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
            width: min(540px, 100%);
            text-align: center;
            z-index: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: clamp(0.45rem, 1.8vh, 0.8rem);
            margin: 0 auto;
            padding: clamp(0.45rem, 1.6vh, 1.1rem) clamp(0.6rem, 2.6vw, 1.35rem);
        }
        h1 {
            font-size: clamp(1.85rem, 6vw, 2.7rem);
            margin: 0 0 clamp(0.4rem, 1.2vh, 0.7rem);
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(120deg, var(--gradient-start), var(--gradient-end));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-size: 200% 200%;
            animation: gradient-shift 6s ease-in-out infinite;
        }
        p.lede {
            font-size: clamp(0.86rem, 2.1vw, 0.96rem);
            color: var(--text-muted);
            margin: 0 auto clamp(0.65rem, 2vh, 1.1rem);
            line-height: 1.48;
            max-width: clamp(32ch, 76%, 44ch);
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.3rem 0.75rem;
            background: rgba(255,255,255,0.035);
            font-size: clamp(0.72rem, 1.9vw, 0.84rem);
            font-weight: 500;
            color: rgba(228,231,244,0.85);
            margin-bottom: clamp(0.55rem, 1.8vh, 0.95rem);
        }
        .logo-frame {
            width: clamp(70px, 14vw, 104px);
            height: clamp(70px, 14vw, 104px);
            border-radius: 50%;
            padding: 0.35rem;
            background: linear-gradient(140deg, rgba(118, 75, 162, 0.9), rgba(102, 126, 234, 0.6));
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: clamp(0.6rem, 1.8vh, 0.9rem);
        }
        .logo-frame img {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            object-fit: cover;
            background: rgba(15, 5, 27, 0.85);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.1);
        }
        .status-dot {
            width: 0.45rem;
            height: 0.45rem;
            border-radius: 50%;
            background: rgba(61, 218, 180, 0.7);
            box-shadow: 0 0 12px rgba(61, 218, 180, 0.25);
        }
        .cta-group {
            display: flex;
            flex-direction: column;
            gap: clamp(0.45rem, 1.6vh, 0.7rem);
            width: 100%;
            align-items: center;
        }
        @media (min-width: 640px) {
            .cta-group { flex-direction: row; justify-content: center; }
        }
        .btn {
            padding: 0.7rem 1.4rem;
            border-radius: 999px;
            border: 1px solid transparent;
            text-decoration: none;
            font-weight: 600;
            font-size: clamp(0.8rem, 1.9vw, 0.9rem);
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            justify-content: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
            min-width: 180px;
        }
        .github-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            margin-bottom: clamp(0.5rem, 1.5vh, 0.9rem);
            transition: color 0.2s ease, transform 0.2s ease;
        }
        .github-link .icon {
            width: 24px;
            height: 24px;
        }
        .github-link:hover {
            color: var(--text-primary);
            transform: translateY(-2px);
        }
        .github-link:active {
            transform: scale(0.95);
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
        .pill-grid {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: clamp(0.45rem, 1.8vw, 0.7rem);
            width: 100%;
        }
        .pill {
            display: inline-flex;
            flex-direction: column;
            gap: 0.15rem;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 18px;
            padding: 0.55rem 0.85rem;
            min-width: 120px;
            max-width: 176px;
            background: rgba(255,255,255,0.05);
            box-shadow: 0 12px 25px rgba(0,0,0,0.25);
        }
        .pill span {
            font-size: clamp(0.68rem, 1.8vw, 0.76rem);
            color: var(--text-muted);
            line-height: 1.3;
        }
        .pill strong {
            font-size: clamp(0.74rem, 1.9vw, 0.84rem);
        }
        footer {
            font-size: clamp(0.7rem, 1.8vw, 0.8rem);
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            align-items: center;
        }
        a.link {
            color: var(--text-primary);
            text-decoration: none;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }
        .footer-links {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
        }
        .legal-section {
            width: min(640px, 100%);
            margin: 0 auto;
            background: rgba(15, 5, 27, 0.6);
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 40px 80px rgba(0,0,0,0.4);
            padding: clamp(1rem, 2.6vw, 1.6rem);
            display: flex;
            flex-direction: column;
            gap: clamp(1.5rem, 2.8vw, 2rem);
        }
        .legal-card {
            display: none;
            flex-direction: column;
        }
        .legal-card.active {
            display: flex;
        }
        .legal-card h2 {
            margin: 0 0 0.8rem;
            font-size: clamp(1.08rem, 2.4vw, 1.32rem);
            color: var(--text-primary);
        }
        .legal-card p {
            margin: 0 0 0.9rem;
            color: var(--text-muted);
            font-size: clamp(0.78rem, 2vw, 0.9rem);
            line-height: 1.55;
        }
        .legal-card p:last-of-type {
            margin-bottom: 0;
        }
        body.modal-open {
            overflow: hidden;
        }
        .modal-root {
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: clamp(1rem, 3vw, 2rem);
            background: rgba(12, 6, 24, 0.78);
            backdrop-filter: blur(12px);
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transition: opacity 0.25s ease;
            z-index: 20;
        }
        .modal-root.active {
            opacity: 1;
            visibility: visible;
            pointer-events: auto;
        }
        .modal-sheet {
            width: min(720px, calc(100vw - clamp(1.5rem, 5vw, 3rem)));
            max-height: min(90vh, 960px);
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 1.2rem;
        }
        .modal-controls {
            display: flex;
            justify-content: flex-end;
            margin-bottom: 1rem;
        }
        .modal-close {
            appearance: none;
            border: 1px solid rgba(255,255,255,0.18);
            background: rgba(255,255,255,0.08);
            color: var(--text-primary);
            border-radius: 999px;
            padding: 0.35rem 0.95rem;
            font-size: 0.78rem;
            font-weight: 500;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: background 0.2s ease, transform 0.2s ease;
        }
        .modal-close:hover {
            background: rgba(255,255,255,0.16);
            transform: translateY(-1px);
        }
        .modal-close:active {
            transform: scale(0.97);
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
        @media (max-width: 640px) {
            .pill {
                min-width: calc(50% - 0.5rem);
                max-width: none;
            }
            .pill strong { font-size: 0.78rem; }
            .pill span { font-size: 0.7rem; }
        }
        @media (max-width: 460px) {
            body {
                padding: clamp(0.6rem, 4.5vw, 1.2rem);
            }
            .cta-group {
                gap: 0.45rem;
            }
            .btn {
                width: 100%;
                min-width: 0;
            }
            .pill {
                min-width: 100%;
            }
        }
        @media (max-height: 720px) {
            main {
                gap: 0.45rem;
                padding-block: clamp(0.4rem, 1.6vh, 0.8rem);
            }
            .logo-frame {
                margin-bottom: 0.65rem;
                width: clamp(64px, 13vw, 96px);
                height: clamp(64px, 13vw, 96px);
            }
            p.lede {
                margin-bottom: clamp(0.5rem, 1.5vh, 0.85rem);
            }
            .pill-grid {
                gap: 0.4rem;
            }
        }
        @media (min-width: 640px) {
            .legal-section {
                padding: clamp(1.4rem, 2.4vw, 2rem);
            }
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
        <div class=\"logo-frame\">
            <img src=\"/static/distask-logo.png\" alt=\"DisTask bot logo\" width=\"132\" height=\"132\" loading=\"lazy\" />
        </div>
        <h1>DisTask</h1>
        <p class=\"lede\">Orchestrate disciplined Discord workflows with kanban clarity, slash-command speed, and reliable reminders that keep every guild project humming.</p>
        <a href=\"https://github.com/NYTEMODEONLY/distask\" target=\"_blank\" rel=\"noopener\" class=\"github-link\" aria-label=\"View DisTask on GitHub\">
            <i data-lucide=\"github\" class=\"icon\"></i>
        </a>
        <div class=\"cta-group\">
            <a class=\"btn btn-primary\" href=\"{{INVITE_URL}}\" target=\"_blank\" rel=\"noopener\">
                <i data-lucide=\"zap\" class=\"icon\"></i>
                Deploy to Discord
            </a>
            <a class=\"btn btn-secondary\" href=\"https://discord.gg/C6nwuT2qpF\" target=\"_blank\" rel=\"noopener\">
                <i data-lucide=\"users\" class=\"icon\"></i>
                Join the Community
            </a>
        </div>
        <div class=\"pill-grid\">
            <div class=\"pill\">
                <strong>Boards</strong>
                <span>Kanban flows fully inside Discord.</span>
            </div>
            <div class=\"pill\">
                <strong>Reminders</strong>
                <span>Digest alerts surface deadlines.</span>
            </div>
            <div class=\"pill\">
                <strong>Permissions</strong>
                <span>Respect server roles for every action.</span>
            </div>
            <div class=\"pill\">
                <strong>Extensible</strong>
                <span>MIT core, async utilities, limitless ideas.</span>
            </div>
        </div>
        <footer>
            <span>Built by <a class=\"link\" href=\"https://nytemode.com\" target=\"_blank\" rel=\"noopener\">nytemode</a> · Status pulses every 10 seconds</span>
            <span class=\"footer-links\">
                <a class=\"link legal-trigger\" href=\"#terms\" data-legal-target=\"terms\">Terms of Use</a>
                <span aria-hidden=\"true\">·</span>
                <a class=\"link legal-trigger\" href=\"#privacy\" data-legal-target=\"privacy\">Privacy Policy</a>
            </span>
        </footer>
    </main>
    <div class=\"modal-root\" id=\"legal-modal\" role=\"dialog\" aria-modal=\"true\" aria-hidden=\"true\">
        <div class=\"modal-sheet\" role=\"document\">
            <div class=\"modal-controls\">
                <button class=\"modal-close\" type=\"button\" id=\"legal-modal-close\" aria-label=\"Close legal information\">Close</button>
            </div>
            <div class=\"legal-section\" id=\"legal-modal-content\" tabindex=\"-1\">
                <article class=\"legal-card\" data-legal=\"terms\" aria-labelledby=\"legal-title-terms\" hidden>
                    <h2 id=\"legal-title-terms\" tabindex=\"-1\">Terms of Use</h2>
                    <p>DisTask provides Discord-native project coordination through task boards, queues, and automated reminders. By adding the bot to your server, you represent that you have permission to connect the workspace and manage the information collected through your guild.</p>
                    <p>Using the bot requires us to persistently store boards, tasks, checklists, reminder schedules, and related audit timestamps on infrastructure operated for DisTask. This storage keeps workflows available across sessions, restarts, and channel changes.</p>
                    <p>You remain responsible for the content submitted through commands, including ensuring that tasks and notes comply with your organization's policies and Discord's community guidelines. We may suspend access if activity risks system integrity or violates platform rules.</p>
                    <p>You may remove DisTask from your server at any time. Doing so stops new data collection and begins the scheduled removal of stored workspace data, subject to reasonable backup and audit requirements.</p>
                </article>
                <article class=\"legal-card\" data-legal=\"privacy\" aria-labelledby=\"legal-title-privacy\" hidden>
                    <h2 id=\"legal-title-privacy\" tabindex=\"-1\">Privacy Policy</h2>
                    <p>When you interact with DisTask, we collect the minimum information needed to run the service: Discord guild, channel, and user identifiers; the content of boards, tasks, tags, attachments metadata, and reminders you create; and operational logs that help us secure the platform.</p>
                    <p>All records are stored on servers dedicated to the DisTask bot so that task lists, board views, and automation remain synchronized across Discord sessions. We do not sell this data or share it with third parties except as required to operate the service or comply with law.</p>
                    <p>Server administrators can use bot commands or support channels to correct or delete items. Removing a task or board will queue it for deletion from our active systems, and full workspace removal occurs after the bot is disconnected, following standard backup retention windows.</p>
                    <p>If you have questions about how your information is handled or need additional assistance, contact the maintainers at <a class=\"link\" href=\"mailto:hello@distask.xyz\">hello@distask.xyz</a>.</p>
                </article>
            </div>
        </div>
    </div>
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
            try {
                const res = await fetch(`/status?ts=${Date.now()}`);
                if (!res.ok) throw new Error('Bad status');
                const data = await res.json();
                dot.style.background = data.color;
                dot.style.boxShadow = `0 0 16px ${data.color}`;
                label.textContent = data.label;
            } catch (err) {
                dot.style.background = 'var(--status-down)';
                label.textContent = 'Status Unknown';
            }
        }
        function setupLegalModal() {
            const legalModal = document.getElementById('legal-modal');
            const closeBtn = document.getElementById('legal-modal-close');
            const modalContent = document.getElementById('legal-modal-content');
            const modalSheet = legalModal ? legalModal.querySelector('.modal-sheet') : null;
            const triggers = Array.from(document.querySelectorAll('[data-legal-target]'));
            if (!legalModal || !closeBtn || !modalContent || !modalSheet || triggers.length === 0) return;
            const cards = Array.from(legalModal.querySelectorAll('.legal-card'));
            const validTargets = new Set(cards.map((card) => card.dataset.legal).filter(Boolean));
            if (validTargets.size === 0) return;
            const baseUrl = `${window.location.pathname}${window.location.search}`;
            let activeTarget = null;
            let lastTrigger = null;
            let modalStatePushed = false;
            function activateCard(target) {
                let activeCard = null;
                cards.forEach((card) => {
                    const isActive = card.dataset.legal === target;
                    card.classList.toggle('active', isActive);
                    card.hidden = !isActive;
                    if (isActive) {
                        activeCard = card;
                    }
                });
                return activeCard;
            }
            function openModal(target, fromHistory = false) {
                if (!validTargets.has(target)) return;
                const activeCardNode = activateCard(target);
                if (!activeCardNode) return;
                const heading = activeCardNode.querySelector('h2');
                if (heading && heading.id) {
                    legalModal.setAttribute('aria-labelledby', heading.id);
                } else {
                    legalModal.removeAttribute('aria-labelledby');
                }
                legalModal.classList.add('active');
                legalModal.setAttribute('aria-hidden', 'false');
                document.body.classList.add('modal-open');
                modalSheet.scrollTop = 0;
                activeTarget = target;
                const focusTarget = heading && typeof heading.focus === 'function' ? heading : modalContent;
                window.requestAnimationFrame(() => {
                    focusTarget.focus({ preventScroll: true });
                });
                if (fromHistory) {
                    const state = window.history.state;
                    modalStatePushed = Boolean(state && state.legalModal === target);
                    lastTrigger = null;
                } else {
                    history.pushState({ legalModal: target }, '', `${baseUrl}#${target}`);
                    modalStatePushed = true;
                }
            }
            function closeModal(fromHistory = false) {
                if (!legalModal.classList.contains('active')) {
                    activeTarget = null;
                    modalStatePushed = false;
                    return;
                }
                legalModal.classList.remove('active');
                legalModal.setAttribute('aria-hidden', 'true');
                legalModal.removeAttribute('aria-labelledby');
                document.body.classList.remove('modal-open');
                cards.forEach((card) => {
                    card.classList.remove('active');
                    card.hidden = true;
                });
                const previousTarget = activeTarget;
                activeTarget = null;
                if (!fromHistory && lastTrigger && typeof lastTrigger.focus === 'function') {
                    lastTrigger.focus();
                }
                lastTrigger = null;
                if (!fromHistory) {
                    if (modalStatePushed) {
                        modalStatePushed = false;
                        history.back();
                    } else if (previousTarget && window.location.hash.replace(/^#/, '') === previousTarget) {
                        history.replaceState(window.history.state, '', baseUrl);
                    }
                } else {
                    modalStatePushed = false;
                }
            }
            triggers.forEach((trigger) => {
                trigger.addEventListener('click', (event) => {
                    event.preventDefault();
                    const target = trigger.getAttribute('data-legal-target');
                    if (!target || !validTargets.has(target)) return;
                    lastTrigger = trigger;
                    if (legalModal.classList.contains('active') && activeTarget === target) {
                        return;
                    }
                    openModal(target);
                });
            });
            closeBtn.addEventListener('click', () => closeModal());
            legalModal.addEventListener('click', (event) => {
                if (event.target === legalModal) {
                    closeModal();
                }
            });
            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && legalModal.classList.contains('active')) {
                    closeModal();
                }
            });
            window.addEventListener('popstate', () => {
                const hash = window.location.hash.replace(/^#/, '');
                if (validTargets.has(hash)) {
                    openModal(hash, true);
                } else {
                    closeModal(true);
                }
            });
            window.addEventListener('hashchange', () => {
                const hash = window.location.hash.replace(/^#/, '');
                if (validTargets.has(hash)) {
                    openModal(hash, true);
                } else {
                    closeModal(true);
                }
            });
            const initialHash = window.location.hash.replace(/^#/, '');
            if (validTargets.has(initialHash)) {
                openModal(initialHash, true);
            }
        }
        document.addEventListener('DOMContentLoaded', () => {
            initParticles();
            if (window.lucide) { window.lucide.createIcons(); }
            refreshStatus();
            setInterval(refreshStatus, 10000);
            setupLegalModal();
        });
    </script>
</body>
</html>
"""

HTML = (
    HTML_TEMPLATE.replace("{{INVITE_URL}}", INVITE_URL)
    .replace("{{DESCRIPTION}}", PAGE_DESCRIPTION)
    .replace("{{CARD_IMAGE}}", CARD_IMAGE)
    .replace("{{CANONICAL_URL}}", CANONICAL_URL)
)


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


def verify_github_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify GitHub webhook signature using HMAC SHA256."""
    if not signature_header:
        return False
    
    # GitHub sends signature as "sha256=<hash>"
    if not signature_header.startswith("sha256="):
        return False
    
    hash_object = hmac.new(secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)


@app.post("/webhooks/github")
async def github_webhook(request: Request, x_hub_signature_256: str | None = Header(None)) -> JSONResponse:
    """
    GitHub webhook endpoint for automatic code sync.
    
    Receives push events from GitHub and triggers git sync script.
    Verifies webhook signature for security.
    """
    # Check if webhook is enabled
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="GitHub webhook not configured (GITHUB_WEBHOOK_SECRET missing)")
    
    # Get raw body for signature verification
    payload_body = await request.body()
    
    # Verify signature
    if not verify_github_signature(payload_body, x_hub_signature_256 or "", webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse payload
    try:
        payload = json.loads(payload_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Check if this is a push event
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        return JSONResponse({"status": "ignored", "reason": f"Event type '{event_type}' not handled"})
    
    # Get branch from payload
    ref = payload.get("ref", "")
    expected_branch = os.getenv("GIT_SYNC_BRANCH", "main")
    
    # Check if push is to the monitored branch
    if not ref.endswith(f"/{expected_branch}"):
        return JSONResponse({
            "status": "ignored",
            "reason": f"Push to '{ref}' not monitored (expected '{expected_branch}')"
        })
    
    # Get sync script path
    repo_root = Path(__file__).resolve().parent.parent
    sync_script = repo_root / "scripts" / "git_sync.py"
    
    if not sync_script.exists():
        raise HTTPException(status_code=500, detail="Sync script not found")
    
    # Trigger sync script asynchronously (don't wait for completion)
    try:
        subprocess.Popen(
            [sys.executable, str(sync_script)],
            cwd=str(repo_root),
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger sync: {str(e)}")
    
    # Return immediately (sync runs in background)
    commit_sha = payload.get("after", "")[:8] if payload.get("after") else "unknown"
    return JSONResponse({
        "status": "accepted",
        "message": f"Sync triggered for commit {commit_sha}",
        "branch": expected_branch,
    })
