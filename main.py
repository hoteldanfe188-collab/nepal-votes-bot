#!/usr/bin/env python3
"""
Nepal Election 2082 - Alert Agent
Source: election.nepsebajar.com
Alerts: Vote Count Update, Lead Change, Winner Declared
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
SOURCE   = "https://election.nepsebajar.com/en"

def ts():      return datetime.now().strftime("%H:%M:%S")
def now_str(): return datetime.now().strftime("%d %b %Y, %I:%M %p")
def log(msg):  print(f"[{ts()}] {msg}", flush=True)

def send_telegram(message):
    try:
        if len(message) > 4096:
            message = message[:4090] + "..."
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10
        )
        log("Sent!" if r.status_code == 200 else f"TG error: {r.status_code}")
    except Exception as e:
        log(f"TG error: {e}")

def fetch_results():
    """
    Scrapes the compact Party Status table from nepsebajar:
      Party | Won | Lead
    Returns dict with standings list, winners list, hash, leading_party
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(SOURCE, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    standings = []  # list of dicts: {party, won, lead}
    winners   = []  # list of "Party — Won: N"

    # Find the compact "Party Status" table (3 columns: Party, Won, Lead)
    for table in soup.find_all("table"):
        ths = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Won" in ths and ("Lead" in ths or "Leading" in ths):
            for row in table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) >= 3:
                    party = tds[0].get_text(strip=True)
                    won   = tds[1].get_text(strip=True)
                    lead  = tds[2].get_text(strip=True)
                    if party and party not in ["Party", "Parties"]:
                        standings.append({"party": party, "won": won, "lead": lead})
                        if won.isdigit() and int(won) > 0:
                            winners.append(f"{party} — Won: {won}")
            break  # only use first matching table

    flat         = "|".join(f"{s['party']}:{s['won']}:{s['lead']}" for s in standings)
    content_hash = hashlib.md5(flat.encode()).hexdigest()
    leading      = standings[0]["party"] if standings else ""

    return {
        "hash":          content_hash,
        "standings":     standings,
        "winners":       winners,
        "leading_party": leading,
    }

def format_table(standings):
    lines = ["<pre>"]
    lines.append(f"{'Party':<30} {'Won':>4} {'Lead':>5}")
    lines.append("─" * 41)
    for s in standings[:10]:
        party = s["party"][:28]
        lines.append(f"{party:<30} {s['won']:>4} {s['lead']:>5}")
    lines.append("</pre>")
    return "\n".join(lines)

def build_startup(data):
    lines = [
        "🇳🇵 <b>NEPAL ELECTION 2082 — CURRENT STATUS</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]
    if data["winners"]:
        lines.append("🏆 <b>DECLARED WINNERS:</b>")
        for w in data["winners"]:
            lines.append(f"    🏅 {w}")
        lines.append("")
    if data["standings"]:
        lines.append("📊 <b>PARTY STANDINGS:</b>")
        lines.append(format_table(data["standings"]))
    else:
        lines.append("⏳ Counting not yet started. Will notify when results come in!")
    lines.append("")
    lines.append(f"🔗 <a href='{SOURCE}'>View Full Live Results →</a>")
    return "\n".join(lines)

def build_winner(data, new_winners):
    lines = [
        "🏆 <b>WINNER DECLARED!</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🎉 <b>New Winner(s):</b>",
    ]
    for w in new_winners:
        lines.append(f"    🏅 {w}")
    lines.append("")
    lines.append("📊 <b>Overall Tally:</b>")
    lines.append(format_table(data["standings"]))
    lines.append("")
    lines.append(f"🔗 <a href='{SOURCE}'>View Full Results →</a>")
    return "\n".join(lines)

def build_lead_change(data, old_data):
    lines = [
        "🚨 <b>LEAD CHANGE!</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"    <i>Before: {old_data['leading_party']}</i>",
        f"    <b>Now leading: {data['leading_party']}</b>",
        "",
        "📊 <b>Current Standings:</b>",
    ]
    lines.append(format_table(data["standings"]))
    lines.append("")
    lines.append(f"🔗 <a href='{SOURCE}'>View Full Results →</a>")
    return "\n".join(lines)

def build_count_update(data):
    lines = [
        "🔔 <b>Vote Count Update</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 <b>Party Standings:</b>",
    ]
    lines.append(format_table(data["standings"]))
    lines.append("")
    lines.append(f"🔗 <a href='{SOURCE}'>View Full Results →</a>")
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
        log("ERROR: Missing env vars"); return

    log(f"Started. Interval: {INTERVAL}s")
    send_telegram(
        "🇳🇵 <b>Nepal Election Alert Bot — Live!</b>\n\n"
        "Fetching current results...\n<i>Please wait.</i>"
    )
    time.sleep(2)

    state = None
    try:
        state = fetch_results()
        send_telegram(build_startup(state))
        log("Startup summary sent!")
    except Exception as e:
        log(f"Startup error: {e}")
        send_telegram("⚠️ Could not fetch results. Will keep retrying...")

    checks = alerts = 0

    while True:
        try:
            log("Checking...")
            data = fetch_results()
            checks += 1
            if state is None:
                state = data
                log("Baseline set.")
            else:
                change, new_winners = detect_change(state, data)
                if change == "win":
                    send_telegram(build_winner(data, new_winners))
                    alerts += 1; state = data
                    log(f"WINNER sent!")
                elif change == "lead_change":
                    send_telegram(build_lead_change(data, state))
                    alerts += 1; state = data
                    log("LEAD CHANGE sent!")
                elif change == "update":
                    send_telegram(build_count_update(data))
                    alerts += 1; state = data
                    log("COUNT UPDATE sent!")
                else:
                    log("No change.")
        except Exception as e:
            log(f"Error: {e}")

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
