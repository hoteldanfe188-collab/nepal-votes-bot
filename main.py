#!/usr/bin/env python3
"""
Nepal Election - Alert Agent (FREE - Telegram Version)
Deployed on Railway.app — runs 24/7 in the cloud.

Environment Variables (set in Railway dashboard):
    TELEGRAM_TOKEN   — your bot token
    TELEGRAM_CHAT_ID — your channel ID
    INTERVAL         — check interval in seconds (default: 60)
"""

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import os
from datetime import datetime

# ── Config from environment variables ─────────────────────────────────────
TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = int(os.environ.get("INTERVAL", "60"))

SITES = [
    {
        "name": "Nepal Votes Live",
        "url": "https://nepalvotes.live",
        "emoji": "🗳"
    },
    {
        "name": "Ekantipur Election",
        "url": "https://election.ekantipur.com/party/7/leading?lng=nep",
        "emoji": "📊"
    }
]

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        if len(message) > 4096:
            message = message[:4090] + "..."
        resp = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }, timeout=10)
        if resp.status_code == 200:
            log("Telegram message sent!")
        else:
            log(f"Telegram error: {resp.status_code} - {resp.text}")
    except Exception as e:
        log(f"Telegram error: {e}")

def fetch_site(site):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(site["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    headlines = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 3:
            headlines.append(text)

    constituencies = []
    for tag in soup.find_all(["li", "tr", "div", "p"]):
        text = tag.get_text(separator=" ", strip=True)
        if any(k in text.lower() for k in ["leading", "won", "ahead", "जित", "अगाडि", "votes", "मत"]):
            if 10 < len(text) < 200:
                constituencies.append(text)

    parties = []
    for tag in soup.find_all(["tr", "li", "div"]):
        text = tag.get_text(separator=" ", strip=True)
        if any(char.isdigit() for char in text) and 5 < len(text) < 150:
            parties.append(text)

    body_text = soup.get_text(separator=" ", strip=True)
    content_hash = hashlib.md5(body_text.encode()).hexdigest()

    return {
        "hash": content_hash,
        "headlines": headlines[:5],
        "constituencies": constituencies[:8],
        "parties": parties[:10],
    }

def detect_change_type(old_data, new_data):
    for h in new_data.get("headlines", []):
        if any(w in h.lower() for w in ["won", "win", "winner", "elected", "जित", "विजयी"]):
            return "win"
    old_const = set(old_data.get("constituencies", []))
    new_const = set(new_data.get("constituencies", []))
    if new_const - old_const:
        return "lead_change"
    return "update"

def build_message(site, data, change_type, old_data=None):
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")

    if change_type == "win":
        header = "🏆 <b>WINNER DECLARED!</b>"
    elif change_type == "lead_change":
        header = "🚨 <b>LEAD CHANGE DETECTED!</b>"
    else:
        header = "🔔 <b>Election Update</b>"

    lines = []
    lines.append(header)
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now}</i>")
    lines.append("")

    if data["headlines"]:
        lines.append("📌 <b>Latest:</b>")
        for h in data["headlines"][:2]:
            lines.append(f"    <i>{h[:120]}</i>")
        lines.append("")

    new_const = data.get("constituencies", [])
    old_const = old_data.get("constituencies", []) if old_data else []
    new_updates = [c for c in new_const if c not in old_const]

    if new_updates:
        lines.append("📍 <b>New Constituency Updates:</b>")
        for c in new_updates[:5]:
            lines.append(f"    • {c[:120]}")
        lines.append("")
    elif new_const:
        lines.append("📍 <b>Top Constituencies:</b>")
        for c in new_const[:5]:
            lines.append(f"    • {c[:120]}")
        lines.append("")

    if data["parties"]:
        lines.append("📊 <b>Party Standings:</b>")
        for p in data["parties"][:5]:
            lines.append(f"    • {p[:120]}")
        lines.append("")

    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")

    return "\n".join(lines)

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set as environment variables!")
        return

    log(f"Agent started. Checking every {INTERVAL}s.")
    log(f"Monitoring {len(SITES)} sites.")

    sites_list = "\n".join([f"{s['emoji']} <b>{s['name']}</b>" for s in SITES])
    send_telegram(
        f"🇳🇵 <b>Nepal Election Alert Agent — Live!</b>\n\n"
        f"Now monitoring:\n{sites_list}\n\n"
        f"⏱ <i>Checking every {INTERVAL} seconds</i>\n\n"
        f"You'll get notified on:\n"
        f"    🔔 Every count update\n"
        f"    🚨 Lead changes\n"
        f"    🏆 Winners declared\n"
        f"    📍 Top constituency results\n\n"
        f"<i>Stay tuned for live updates!</i>"
    )

    states = {site["url"]: None for site in SITES}
    checks = 0
    alerts = 0

    while True:
        for site in SITES:
            try:
                log(f"Checking {site['name']}...")
                data = fetch_site(site)
                url = site["url"]
                checks += 1

                if states[url] is None:
                    states[url] = data
                    log(f"Baseline for {site['name']} captured.")
                    msg = build_message(site, data, "update", None)
                    send_telegram(msg)

                elif data["hash"] != states[url]["hash"]:
                    alerts += 1
                    change_type = detect_change_type(states[url], data)
                    msg = build_message(site, data, change_type, states[url])
                    send_telegram(msg)
                    log(f"CHANGE on {site['name']} [{change_type}]!")
                    states[url] = data
                else:
                    log(f"No changes on {site['name']}.")

            except Exception as e:
                log(f"Error on {site['name']}: {e}")

            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next round in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
