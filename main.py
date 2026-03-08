#!/usr/bin/env python3
"""
Nepal Election 2082 - Alert Agent
Notifications: Winner, Lead Change, Vote Count Update, Samanupatik Update
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

# Party symbols mapping
SYMBOLS = {
    "rastriya swatantra": "🔔",
    "nepali congress":    "🌳",
    "nepal communist party (uml)": "☀️",
    "nepali communist party":      "⭐",
    "shram sanskriti":    "🤲",
    "rastriya prajatantra": "🌾",
    "ujyalo nepal":       "💡",
    "janata samajwadi":   "☂️",
    "independent":        "🧑",
    "progressive democratic": "🏴",
}

def get_symbol(party_name):
    pl = party_name.lower()
    for key, sym in SYMBOLS.items():
        if key in pl:
            return sym
    return "🔹"

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
        log("Sent!" if r.status_code == 200 else f"TG error: {r.status_code} {r.text[:100]}")
    except Exception as e:
        log(f"TG error: {e}")

def fetch_results():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(SOURCE, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    standings = []  # FPTP: party, won, lead
    pr_votes  = []  # Samanupatik: party, votes
    winners   = []

    # ── Table 1: compact Party Status (Party | Won | Lead) ──
    for table in soup.find_all("table"):
        text = table.get_text()
        if "Won" in text and "Lead" in text and "PR" not in text:
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 3:
                    party = cells[0].get_text(strip=True)
                    col1  = cells[1].get_text(strip=True)
                    col2  = cells[2].get_text(strip=True)
                    if party.lower() in ["party", "parties", ""] or col1.lower() in ["won", "lead"]:
                        continue
                    won  = col1 if col1 not in ["-", ""] else "0"
                    lead = col2 if col2 not in ["-", ""] else "0"
                    standings.append({"party": party, "won": won, "lead": lead})
                    if won.isdigit() and int(won) > 0:
                        winners.append(f"{party} — Won: {won}, Leading: {lead}")
            if standings:
                break

    # ── Table 2: big detailed table — Party | Lead | Win | PR Seat | Total | Win | Total PR Votes ──
    for table in soup.find_all("table"):
        text = table.get_text()
        if "Total PR Votes" in text:
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 6:
                    party  = cells[0].get_text(strip=True)
                    pr_col = cells[-1].get_text(strip=True)  # last col = Total PR Votes
                    if not party or party.lower() in ["parties", "party", "leading", "win"]:
                        continue
                    if pr_col in ["-", "", "Total PR Votes"] or not any(c.isdigit() for c in pr_col):
                        continue
                    pr_votes.append({"party": party, "votes": pr_col})
            break

    log(f"Scraped: {len(standings)} parties, {len(pr_votes)} PR entries, {len(winners)} winners")

    flat_fptp = "|".join(f"{s['party']}:{s['won']}:{s['lead']}" for s in standings)
    flat_pr   = "|".join(f"{p['party']}:{p['votes']}" for p in pr_votes)
    hash_fptp = hashlib.md5(flat_fptp.encode()).hexdigest()
    hash_pr   = hashlib.md5(flat_pr.encode()).hexdigest()
    leading   = standings[0]["party"] if standings else ""

    return {
        "hash_fptp":     hash_fptp,
        "hash_pr":       hash_pr,
        "standings":     standings,
        "pr_votes":      pr_votes,
        "winners":       winners,
        "leading_party": leading,
    }

def fmt_standings(standings):
    lines = ["<pre>"]
    lines.append(f"{'Party':<28} {'Won':>4} {'Lead':>5}")
    lines.append("─" * 39)
    for s in standings[:10]:
        p = s["party"][:26]
        lines.append(f"{p:<28} {s['won']:>4} {s['lead']:>5}")
    lines.append("</pre>")
    return "\n".join(lines)

def msg_startup(data):
    lines = [
        "🇳🇵 <b>NEPAL ELECTION 2082 — LIVE STATUS</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━", ""
    ]
    if data["winners"]:
        lines.append("🏆 <b>WINNERS SO FAR:</b>")
        for w in data["winners"][:5]: lines.append(f"  🏅 {w}")
        lines.append("")
    if data["standings"]:
        lines.append("📊 <b>PARTY STANDINGS (Won / Lead):</b>")
        lines.append(fmt_standings(data["standings"]))
    else:
        lines.append("⏳ No data yet — will notify as results come in!")
    lines += ["", f"🔗 <a href='{SOURCE}'>Full Live Results →</a>"]
    return "\n".join(lines)

def msg_winner(data, new_winners):
    lines = [
        "🏆 <b>WINNER DECLARED!</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━", "",
        "🎉 <b>New Winner(s):</b>"
    ]
    for w in new_winners: lines.append(f"  🏅 {w}")
    lines += ["", "📊 <b>Overall Tally:</b>",
              fmt_standings(data["standings"]),
              "", f"🔗 <a href='{SOURCE}'>Full Results →</a>"]
    return "\n".join(lines)

def msg_lead_change(data, old):
    lines = [
        "🚨 <b>LEAD CHANGE!</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━", "",
        f"  <i>Was: {old['leading_party']}</i>",
        f"  <b>Now: {data['leading_party']}</b>",
        "", "📊 <b>Current Standings:</b>",
        fmt_standings(data["standings"]),
        "", f"🔗 <a href='{SOURCE}'>Full Results →</a>"
    ]
    return "\n".join(lines)

def msg_update(data):
    lines = [
        "🔔 <b>Vote Count Update</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━", "",
        "📊 <b>Party Standings (Won / Lead):</b>",
        fmt_standings(data["standings"]),
        "", f"🔗 <a href='{SOURCE}'>Full Results →</a>"
    ]
    return "\n".join(lines)

def msg_pr_update(data):
    lines = [
        "🗳 <b>समानुपातिक मत अपडेट</b>",
        "<b>Samanupatik (PR) Vote Count</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]
    for p in data["pr_votes"]:
        sym = get_symbol(p["party"])
        lines.append(f"{sym} <b>{p['party']}</b>  —  {p['votes']} votes")
    return "\n".join(lines)

def detect(old, new):
    new_w = [w for w in new["winners"] if w not in old["winners"]]
    if new_w: return "win", new_w
    if old["leading_party"] and new["leading_party"] and old["leading_party"] != new["leading_party"]:
        return "lead_change", []
    if old["hash_fptp"] != new["hash_fptp"]: return "update", []
    return "none", []

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: Missing env vars"); return

    log(f"Started. Interval: {INTERVAL}s")
    send_telegram("🇳🇵 <b>Nepal Election Alert Bot — Starting...</b>\nFetching results, please wait...")
    time.sleep(2)

    state = None
    try:
        state = fetch_results()
        send_telegram(msg_startup(state))
        # Also send PR votes on startup if available
        if state["pr_votes"]:
            time.sleep(2)
            send_telegram(msg_pr_update(state))
        log("Startup done!")
    except Exception as e:
        log(f"Startup error: {e}")
        send_telegram(f"⚠️ Startup fetch failed: {e}")

    checks = alerts = 0
    while True:
        try:
            data = fetch_results()
            checks += 1
            if state is None:
                state = data
            else:
                # FPTP change check
                change, new_w = detect(state, data)
                if change == "win":
                    send_telegram(msg_winner(data, new_w))
                    alerts += 1; state = data; log("WINNER!")
                elif change == "lead_change":
                    send_telegram(msg_lead_change(data, state))
                    alerts += 1; state = data; log("LEAD CHANGE!")
                elif change == "update":
                    send_telegram(msg_update(data))
                    alerts += 1; state = data; log("UPDATE!")
                else:
                    log("No FPTP change.")

                # PR votes change check (separate notification)
                if state["hash_pr"] != data["hash_pr"] and data["pr_votes"]:
                    time.sleep(2)
                    send_telegram(msg_pr_update(data))
                    alerts += 1
                    state = data
                    log("PR UPDATE!")

        except Exception as e:
            log(f"Error: {e}")
        log(f"Checks:{checks} Alerts:{alerts} Next:{INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
