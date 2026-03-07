#!/usr/bin/env python3
"""
Nepal Election - Alert Agent
Startup: sends current standings table
Ongoing: vote counts, lead changes, winners
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

SITES = [
    {"name": "Nepal Votes Live",    "url": "https://nepalvotes.live",                                 "emoji": "🗳"},
    {"name": "Ekantipur Election",  "url": "https://election.ekantipur.com/party/7/leading?lng=nep", "emoji": "📊"},
    {"name": "Election Commission", "url": "https://result.election.gov.np/",                        "emoji": "🏛"},
    {"name": "Nepal Election Live", "url": "https://www.nepalelection.live/",                        "emoji": "🗺"},
]

# Known parties to look for in standings
PARTY_KEYWORDS = [
    ("RSP", ["rsp", "rastriya swatantra", "स्वतन्त्र"]),
    ("NC", ["nepali congress", "nc ", "कांग्रेस"]),
    ("CPN-UML", ["uml", "एमाले", "cpn-uml"]),
    ("NCP", ["ncp", "माओवादी", "maoist"]),
    ("RPP", ["rpp", "rastriya prajatantra"]),
    ("JSP", ["janta samajwadi", "jsp"]),
    ("Independent", ["independent", "स्वतन्त्र उम्मेद"]),
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

def extract_vote_numbers(soup):
    results = []
    for tag in soup.find_all(["tr", "li", "div", "p", "span"]):
        text = tag.get_text(separator=" ", strip=True)
        if re.search(r'\d{1,3},\d{3}', text) or re.search(r'\d{4,}', text):
            if any(bad in text.lower() for bad in [
                "प्रतिनिधिसभा प्रदेश कोशी प्रदेश मधेस",
                "cookie", "copyright", "menu", "login", "register"
            ]):
                continue
            if 5 < len(text) < 180:
                results.append(text)
    return results[:10]

def extract_party_standings(soup):
    standings = []
    for tag in soup.find_all(["tr", "div", "li"]):
        text = tag.get_text(separator=" ", strip=True)
        if re.search(r'\d+', text) and any(k in text.lower() for k in [
            "uml", "nc", "rsp", "rpp", "माओवादी", "एमाले", "कांग्रेस",
            "rastriya", "swatantra", "party", "पार्टी", "दल",
            "won", "leading", "जित", "अगाडि", "seats", "सिट"
        ]):
            if 5 < len(text) < 150:
                standings.append(text)
    return standings[:8]

def extract_winners(soup):
    winners = []
    for tag in soup.find_all(["h1","h2","h3","h4","p","div","li","span"]):
        text = tag.get_text(separator=" ", strip=True)
        if any(w in text.lower() for w in ["won", "winner", "elected", "जित", "विजयी", "निर्वाचित"]):
            if 10 < len(text) < 250:
                winners.append(text)
    return winners[:5]

def fetch_site(site):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(site["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    vote_counts   = extract_vote_numbers(soup)
    standings     = extract_party_standings(soup)
    winners       = extract_winners(soup)
    leading_party = standings[0][:80] if standings else ""
    meaningful    = " ".join(vote_counts + standings)
    content_hash  = hashlib.md5(meaningful.encode()).hexdigest()
    return {
        "hash": content_hash, "vote_counts": vote_counts,
        "standings": standings, "winners": winners, "leading_party": leading_party,
    }

def detect_change_type(old, new):
    new_winners = [w for w in new.get("winners", []) if w not in old.get("winners", [])]
    if new_winners:
        return "win", new_winners
    if old.get("leading_party") and new.get("leading_party"):
        if old["leading_party"] != new["leading_party"]:
            return "lead_change", []
    if old.get("vote_counts") != new.get("vote_counts"):
        return "update", []
    return "none", []

def build_startup_summary(all_data):
    """Build a clean party-wise lead/win table from all sites combined"""
    # Collect all standings and vote counts across sites
    all_standings = []
    all_counts    = []
    all_winners   = []
    for site_url, data in all_data.items():
        if data:
            all_standings += data.get("standings", [])
            all_counts    += data.get("vote_counts", [])
            all_winners   += data.get("winners", [])

    # Deduplicate
    all_standings = list(dict.fromkeys(all_standings))
    all_counts    = list(dict.fromkeys(all_counts))
    all_winners   = list(dict.fromkeys(all_winners))

    lines = []
    lines.append(f"🇳🇵 <b>NEPAL ELECTION 2082 — CURRENT STATUS</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    if all_winners:
        lines.append("🏆 <b>DECLARED WINNERS:</b>")
        for w in all_winners[:5]:
            lines.append(f"    🏅 {w[:180]}")
        lines.append("")

    if all_standings:
        lines.append("📊 <b>PARTY STANDINGS (Lead / Win):</b>")
        lines.append("<pre>")
        lines.append(f"{'Party':<20} {'Lead':>6} {'Win':>6}")
        lines.append("─" * 34)
        seen = set()
        for s in all_standings:
            if s not in seen:
                seen.add(s)
                lines.append(f"  {s[:32]}")
        lines.append("</pre>")
        lines.append("")

    if all_counts:
        lines.append("🗳 <b>LATEST VOTE COUNTS:</b>")
        for c in all_counts[:5]:
            lines.append(f"    • {c[:150]}")
        lines.append("")

    if not all_standings and not all_counts and not all_winners:
        lines.append("⏳ <b>Counting not yet started or no data available.</b>")
        lines.append("    The bot will notify you as soon as results come in!")
        lines.append("")

    lines.append("🔗 <b>Live Sources:</b>")
    for site in SITES:
        lines.append(f"    {site['emoji']} <a href='{site['url']}'>{site['name']}</a>")

    return "\n".join(lines)

def build_regular_update(site, data, old_data):
    new_counts  = [c for c in data["vote_counts"] if c not in old_data.get("vote_counts", [])]
    show_counts = new_counts[:5] if new_counts else data["vote_counts"][:5]
    lines = [f"🔔 <b>Vote Count Update</b>", f"{site['emoji']} <b>{site['name']}</b>",
             f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", ""]
    if show_counts:
        lines.append("🗳 <b>Latest Vote Counts:</b>")
        for c in show_counts: lines.append(f"    • {c[:150]}")
        lines.append("")
    if data["standings"]:
        lines.append("📊 <b>Party Standings:</b>")
        for s in data["standings"][:5]: lines.append(f"    • {s[:150]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_lead_change(site, data, old_data):
    lines = [f"🚨 <b>LEAD CHANGE!</b>", f"{site['emoji']} <b>{site['name']}</b>",
             f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", "", "⚡ <b>The lead has changed!</b>"]
    if old_data.get("leading_party"): lines.append(f"    <i>Before: {old_data['leading_party'][:120]}</i>")
    if data.get("leading_party"):     lines.append(f"    <b>Now: {data['leading_party'][:120]}</b>")
    lines.append("")
    if data["vote_counts"]:
        lines.append("🗳 <b>Latest Counts:</b>")
        for c in data["vote_counts"][:5]: lines.append(f"    • {c[:150]}")
        lines.append("")
    if data["standings"]:
        lines.append("📊 <b>Current Standings:</b>")
        for s in data["standings"][:5]: lines.append(f"    • {s[:150]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_winner_declared(site, data, new_winners):
    lines = [f"🏆 <b>WINNER DECLARED!</b>", f"{site['emoji']} <b>{site['name']}</b>",
             f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", "", "🎉 <b>Winner(s):</b>"]
    for w in new_winners[:3]: lines.append(f"    🏅 {w[:200]}")
    lines.append("")
    if data["standings"]:
        lines.append("📊 <b>Overall Tally:</b>")
        for s in data["standings"][:5]: lines.append(f"    • {s[:150]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set!")
        return

    log(f"Agent started. Checking every {INTERVAL}s.")

    # --- Startup: fetch all sites and send current summary ---
    send_telegram(
        f"🇳🇵 <b>Nepal Election Alert Bot — Starting up...</b>\n\n"
        f"Fetching latest results from {len(SITES)} sources...\n"
        f"<i>Please wait a moment.</i>"
    )
    time.sleep(2)

    site_states = {site["url"]: None for site in SITES}

    # Fetch baseline for all sites
    for site in SITES:
        try:
            log(f"Fetching startup data: {site['name']}...")
            data = fetch_site(site)
            site_states[site["url"]] = data
            log(f"Startup data for {site['name']} ready.")
        except Exception as e:
            log(f"Startup fetch error {site['name']}: {e}")
        time.sleep(2)

    # Send combined current status
    summary = build_startup_summary(site_states)
    send_telegram(summary)
    log("Startup summary sent!")

    checks = 0
    alerts = 0

    while True:
        for site in SITES:
            try:
                log(f"Checking {site['name']}...")
                data = fetch_site(site)
                url  = site["url"]
                checks += 1

                old = site_states[url]
                if old is None:
                    site_states[url] = data
                    log(f"Baseline for {site['name']} captured.")
                else:
                    change_type, new_winners = detect_change_type(old, data)
                    if change_type == "win":
                        send_telegram(build_winner_declared(site, data, new_winners))
                        alerts += 1; site_states[url] = data
                    elif change_type == "lead_change":
                        send_telegram(build_lead_change(site, data, old))
                        alerts += 1; site_states[url] = data
                    elif change_type == "update":
                        send_telegram(build_regular_update(site, data, old))
                        alerts += 1; site_states[url] = data
                    else:
                        log(f"No meaningful change on {site['name']}.")
            except Exception as e:
                log(f"Error on {site['name']}: {e}")
            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
