#!/usr/bin/env python3
"""
Nepal Election - Advanced Alert Agent
Three notification types: Regular Update, Lead Change, Winner Declared
Deployed on Railway.app — runs 24/7
"""

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import os
from datetime import datetime

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

def now_str():
    return datetime.now().strftime("%d %b %Y, %I:%M %p")

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

    winners = []
    for tag in soup.find_all(["h1","h2","h3","h4","p","div","li","span"]):
        text = tag.get_text(separator=" ", strip=True)
        if any(w in text.lower() for w in ["won", "winner", "elected", "जित", "विजयी", "निर्वाचित"]):
            if 5 < len(text) < 250:
                winners.append(text)

    leading_party = ""
    if parties:
        leading_party = parties[0][:80]

    body_text = soup.get_text(separator=" ", strip=True)
    content_hash = hashlib.md5(body_text.encode()).hexdigest()

    return {
        "hash": content_hash,
        "headlines": headlines[:5],
        "constituencies": constituencies[:8],
        "parties": parties[:8],
        "winners": winners[:5],
        "leading_party": leading_party,
    }

def detect_change_type(old, new):
    new_winners = [w for w in new.get("winners", []) if w not in old.get("winners", [])]
    if new_winners:
        return "win", new_winners
    if old.get("leading_party") and new.get("leading_party"):
        if old["leading_party"] != new["leading_party"]:
            return "lead_change", []
    return "update", []

def build_regular_update(site, data, old_data):
    new_const = [c for c in data["constituencies"] if c not in old_data.get("constituencies", [])]
    show_const = new_const[:5] if new_const else data["constituencies"][:5]

    lines = []
    lines.append(f"🔔 <b>Election Update</b>")
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if data["headlines"]:
        lines.append(f"📌 <b>Latest:</b>")
        for h in data["headlines"][:2]:
            lines.append(f"    <i>{h[:120]}</i>")
        lines.append("")
    if show_const:
        lines.append(f"📍 <b>Constituency Updates:</b>")
        for c in show_const:
            lines.append(f"    • {c[:120]}")
        lines.append("")
    if data["parties"]:
        lines.append(f"📊 <b>Party Standings:</b>")
        for p in data["parties"][:5]:
            lines.append(f"    • {p[:120]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_lead_change(site, data, old_data):
    lines = []
    lines.append(f"🚨 <b>LEAD CHANGE DETECTED!</b>")
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"⚡ <b>The lead has changed!</b>")
    if old_data.get("leading_party"):
        lines.append(f"    <i>Before: {old_data['leading_party'][:100]}</i>")
    if data.get("leading_party"):
        lines.append(f"    <b>Now: {data['leading_party'][:100]}</b>")
    lines.append("")
    new_const = [c for c in data["constituencies"] if c not in old_data.get("constituencies", [])]
    if new_const:
        lines.append(f"📍 <b>Latest Constituency Changes:</b>")
        for c in new_const[:5]:
            lines.append(f"    • {c[:120]}")
        lines.append("")
    if data["parties"]:
        lines.append(f"📊 <b>Current Standings:</b>")
        for p in data["parties"][:5]:
            lines.append(f"    • {p[:120]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_winner_declared(site, data, new_winners):
    lines = []
    lines.append(f"🏆 <b>WINNER DECLARED!</b>")
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"🎉 <b>New Winner(s):</b>")
    for w in new_winners[:3]:
        lines.append(f"    🏅 {w[:150]}")
    lines.append("")
    if data["headlines"]:
        lines.append(f"📌 <b>Latest Headlines:</b>")
        for h in data["headlines"][:2]:
            lines.append(f"    <i>{h[:120]}</i>")
        lines.append("")
    if data["parties"]:
        lines.append(f"📊 <b>Overall Tally So Far:</b>")
        for p in data["parties"][:5]:
            lines.append(f"    • {p[:120]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def send_sample_notifications():
    """Send 3 sample notifications to test the bot"""
    log("Sending sample notifications...")

    send_telegram(
        f"🔔 <b>Election Update</b>\n"
        f"🗳 <b>Nepal Votes Live</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 <b>Latest:</b>\n"
        f"    <i>CPN-UML leading in 45 constituencies</i>\n"
        f"    <i>NC ahead in 38 constituencies</i>\n\n"
        f"📍 <b>Constituency Updates:</b>\n"
        f"    • Kathmandu-3: UML leading by 1,200 votes\n"
        f"    • Lalitpur-2: NC ahead by 890 votes\n"
        f"    • Bhaktapur-1: RPP leading by 450 votes\n\n"
        f"📊 <b>Party Standings:</b>\n"
        f"    • CPN-UML: 45 leading, 12 won\n"
        f"    • NC: 38 leading, 8 won\n"
        f"    • RPP: 15 leading, 3 won\n\n"
        f"🔗 <a href='https://nepalvotes.live'>View Full Results →</a>"
    )

    time.sleep(2)

    send_telegram(
        f"🚨 <b>LEAD CHANGE DETECTED!</b>\n"
        f"🗳 <b>Nepal Votes Live</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>The lead has changed!</b>\n"
        f"    <i>Before: CPN-UML leading with 45 seats</i>\n"
        f"    <b>Now: NC overtakes with 46 seats!</b>\n\n"
        f"📍 <b>Latest Constituency Changes:</b>\n"
        f"    • Kathmandu-5: NC overtakes UML by 50 votes!\n"
        f"    • Pokhara-2: UML leads by 120 votes\n"
        f"    • Chitwan-1: NC leads by 340 votes\n\n"
        f"📊 <b>Current Standings:</b>\n"
        f"    • NC: 46 leading\n"
        f"    • CPN-UML: 45 leading\n"
        f"    • RPP: 15 leading\n\n"
        f"🔗 <a href='https://nepalvotes.live'>View Full Results →</a>"
    )

    time.sleep(2)

    send_telegram(
        f"🏆 <b>WINNER DECLARED!</b>\n"
        f"🗳 <b>Nepal Votes Live</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎉 <b>New Winner(s):</b>\n"
        f"    🏅 Ram Bahadur Thapa (CPN-UML) elected from Kathmandu-3!\n"
        f"    Final votes: 12,450 | Margin: 2,340\n\n"
        f"📌 <b>Latest Headlines:</b>\n"
        f"    <i>CPN-UML wins Kathmandu-3 by landslide</i>\n\n"
        f"📊 <b>Overall Tally So Far:</b>\n"
        f"    • CPN-UML: 67 seats\n"
        f"    • NC: 54 seats\n"
        f"    • RPP: 21 seats\n\n"
        f"🔗 <a href='https://nepalvotes.live'>View Full Results →</a>"
    )

    log("Sample notifications sent!")

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set!")
        return

    log(f"Agent started. Checking every {INTERVAL}s.")

    sites_list = "\n".join([f"{s['emoji']} <b>{s['name']}</b>" for s in SITES])
    send_telegram(
        f"🇳🇵 <b>Nepal Election Alert Agent — Live!</b>\n\n"
        f"Now monitoring:\n{sites_list}\n\n"
        f"⏱ <i>Checking every {INTERVAL} seconds</i>\n\n"
        f"Notification types:\n"
        f"    🔔 Regular count updates\n"
        f"    🚨 Lead change alerts\n"
        f"    🏆 Winner declared alerts\n\n"
        f"<i>Stay tuned for live updates!</i>"
    )

    # TEMP: Send sample notifications to preview all 3 types
    send_sample_notifications()

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
                    msg = build_regular_update(site, data, {})
                    send_telegram(msg)

                elif data["hash"] != states[url]["hash"]:
                    alerts += 1
                    change_type, new_winners = detect_change_type(states[url], data)

                    if change_type == "win":
                        msg = build_winner_declared(site, data, new_winners)
                        log(f"WINNER DECLARED on {site['name']}!")
                    elif change_type == "lead_change":
                        msg = build_lead_change(site, data, states[url])
                        log(f"LEAD CHANGE on {site['name']}!")
                    else:
                        msg = build_regular_update(site, data, states[url])
                        log(f"UPDATE on {site['name']}.")

                    send_telegram(msg)
                    states[url] = data
                else:
                    log(f"No changes on {site['name']}.")

            except Exception as e:
                log(f"Error on {site['name']}: {e}")

            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
