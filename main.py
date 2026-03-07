#!/usr/bin/env python3
"""
Nepal Election 2082 - Alert Agent
Primary source: election.nepsebajar.com (real HTML data)
"""

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import os
import re
from datetime import datetime

TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = int(os.environ.get("INTERVAL", "60"))

PRIMARY_URL = "https://election.nepsebajar.com/en"

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
            "chat_id": CHAT_ID, "text": message,
            "parse_mode": "HTML", "disable_web_page_preview": False
        }, timeout=10)
        if resp.status_code == 200:
            log("Sent!")
        else:
            log(f"Telegram error: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        log(f"Telegram error: {e}")

def fetch_results():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(PRIMARY_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    standings = []  # {party, leading, won}
    winners   = []

    # Parse the Party Status table (compact one at top)
    for table in soup.find_all("table"):
        headers_row = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Won" in headers_row or "Lead" in headers_row or "Leading" in headers_row:
            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    party = cells[0]
                    # skip header-like rows
                    if any(h in party for h in ["Party", "Parties", "दल"]):
                        continue
                    if len(party) > 2 and not party.isdigit():
                        standings.append(cells)
                        # Check for wins
                        if len(cells) >= 2 and cells[1].isdigit() and int(cells[1]) > 0:
                            winners.append(f"{party} — Won: {cells[1]}")

    # Build hash from standings
    flat = " ".join([" ".join(s) for s in standings])
    content_hash = hashlib.md5(flat.encode()).hexdigest()

    # Leading party = first row with biggest lead number
    leading_party = standings[0][0] if standings else ""

    return {
        "hash":          content_hash,
        "standings":     standings,
        "winners":       winners,
        "leading_party": leading_party,
    }

def build_standings_table(standings):
    """Format standings as a clean table"""
    lines = []
    lines.append("<pre>")
    lines.append(f"{'Party':<26} {'Lead':>5} {'Won':>4}")
    lines.append("─" * 37)
    for row in standings[:10]:
        party = row[0][:24] if row[0] else ""
        won   = row[1] if len(row) > 1 else "-"
        lead  = row[2] if len(row) > 2 else "-"
        lines.append(f"{party:<26} {lead:>5} {won:>4}")
    lines.append("</pre>")
    return "\n".join(lines)

def build_startup_summary(data):
    lines = [
        "🇳🇵 <b>NEPAL ELECTION 2082 — CURRENT STATUS</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    if data["winners"]:
        lines.append("🏆 <b>DECLARED WINNERS:</b>")
        for w in data["winners"][:5]:
            lines.append(f"    🏅 {w}")
        lines.append("")

    if data["standings"]:
        lines.append("📊 <b>PARTY STANDINGS (Lead / Won):</b>")
        lines.append(build_standings_table(data["standings"]))
        lines.append("")
    else:
        lines.append("⏳ <b>No results yet. Will notify when counting starts!</b>")
        lines.append("")

    lines.append(f"🔗 <a href='{PRIMARY_URL}'>View Full Live Results →</a>")
    return "\n".join(lines)

def build_update_message(data, old_data, change_type, new_winners):
    if change_type == "win":
        header = "🏆 <b>NEW WINNER(S) DECLARED!</b>"
    elif change_type == "lead_change":
        header = "🚨 <b>LEAD CHANGE!</b>"
    else:
        header = "🔔 <b>Vote Count Update</b>"

    lines = [
        header,
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    if change_type == "win" and new_winners:
        lines.append("🎉 <b>New Winner(s):</b>")
        for w in new_winners[:3]:
            lines.append(f"    🏅 {w}")
        lines.append("")

    if change_type == "lead_change":
        lines.append(f"    <i>Before: {old_data.get('leading_party','')[:80]}</i>")
        lines.append(f"    <b>Now: {data.get('leading_party','')[:80]}</b>")
        lines.append("")

    if data["standings"]:
        lines.append("📊 <b>Current Standings (Lead / Won):</b>")
        lines.append(build_standings_table(data["standings"]))
        lines.append("")

    lines.append(f"🔗 <a href='{PRIMARY_URL}'>View Full Live Results →</a>")
    return "\n".join(lines)

def detect_change(old, new):
    new_winners = [w for w in new["winners"] if w not in old["winners"]]
    if new_winners:
        return "win", new_winners
    if old["leading_party"] and new["leading_party"] and old["leading_party"] != new["leading_party"]:
        return "lead_change", []
    if old["hash"] != new["hash"]:
        return "update", []
    return "none", []

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return

    log(f"Agent started. Interval: {INTERVAL}s")

    send_telegram(
        "🇳🇵 <b>Nepal Election Alert Bot — Starting up...</b>\n\n"
        "Fetching latest results...\n<i>Please wait.</i>"
    )
    time.sleep(2)

    # Startup fetch
    try:
        state = fetch_results()
        send_telegram(build_startup_summary(state))
        log("Startup summary sent!")
    except Exception as e:
        log(f"Startup error: {e}")
        send_telegram("⚠️ Could not fetch results at startup. Will keep trying...")
        state = None

    checks = 0
    alerts = 0

    while True:
        try:
            log("Checking results...")
            data = fetch_results()
            checks += 1

            if state is None:
                state = data
                log("Baseline captured.")
            else:
                change_type, new_winners = detect_change(state, data)
                if change_type != "none":
                    send_telegram(build_update_message(data, state, change_type, new_winners))
                    alerts += 1
                    state = data
                    log(f"{change_type.upper()} detected and sent!")
                else:
                    log("No change.")
        except Exception as e:
            log(f"Error: {e}")

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
