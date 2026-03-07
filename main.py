#!/usr/bin/env python3
"""
Nepal Election - Alert Agent
Scrapes election.ekantipur.com + result.election.gov.np properly
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

# Only sites that serve real HTML data (not JS-rendered)
SITES = [
    {
        "name": "Nepal Votes Live",
        "url":  "https://nepalvotes.live",
        "emoji": "🗳",
        "type": "generic"
    },
    {
        "name": "Ekantipur Election",
        "url":  "https://election.ekantipur.com/party/7/leading?lng=eng",
        "emoji": "📊",
        "type": "ekantipur"
    },
    {
        "name": "Election Commission Nepal",
        "url":  "https://result.election.gov.np/",
        "emoji": "🏛",
        "type": "ecn"
    },
    {
        "name": "Nepal Election Live",
        "url":  "https://www.nepalelection.live/",
        "emoji": "🗺",
        "type": "generic"
    },
]

JUNK = [
    "2074", "2079", "federal parliament", "provincial election 2", "local election 20",
    "cookie", "copyright", "privacy", "contact", "about", "login", "register",
    "advertisement", "subscribe", "newsletter", "loading", "javascript",
    "data source", "nepalvotes.live", "click vा tap", "click or tap",
    "hot seat", "most watched", "province-level", "detailed results",
    "समानुपातिक", "निर्वाचित उम्मेदवारहरुको विस्तृत",
    "पहिलो हुने निर्वाचित हुने निर्वाचनमा मतगणनाको आधारमा दलगत स्थिति",
    "© 20", "privacy policy",
]

PARTIES = ["RSP", "NC", "UML", "NCP", "RPP", "JSP", "CPN", "Congress",
           "Maoist", "एमाले", "कांग्रेस", "माओवादी", "स्वतन्त्र",
           "Swatantra", "Rastriya", "Independent"]

def ts():
    return datetime.now().strftime("%H:%M:%S")
def now_str():
    return datetime.now().strftime("%d %b %Y, %I:%M %p")
def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def is_junk(text):
    tl = text.lower()
    return any(j.lower() in tl for j in JUNK)

def has_party(text):
    return any(p.lower() in text.lower() for p in PARTIES)

def has_number(text):
    return bool(re.search(r'\d+', text))

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

def fetch_ekantipur():
    """Scrape Ekantipur election page - party standings table"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(
        "https://election.ekantipur.com/party/7/leading?lng=eng",
        headers=headers, timeout=15
    )
    soup = BeautifulSoup(resp.text, "html.parser")

    standings = []
    winners   = []

    # Try table rows first
    for row in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
        if len(cells) >= 2:
            text = " | ".join(c for c in cells if c)
            if has_party(text) and has_number(text) and not is_junk(text) and len(text) < 200:
                standings.append(text)
                if any(w in text.lower() for w in ["won", "win", "elected", "जित"]):
                    winners.append(text)

    # Try list items / divs with party names
    if not standings:
        for tag in soup.find_all(["li", "div", "p", "span"]):
            text = tag.get_text(separator=" ", strip=True)
            if has_party(text) and has_number(text) and not is_junk(text) and 5 < len(text) < 150:
                standings.append(text)

    standings = list(dict.fromkeys(standings))[:10]
    winners   = list(dict.fromkeys(winners))[:5]

    meaningful   = " ".join(standings)
    content_hash = hashlib.md5(meaningful.encode()).hexdigest()

    return {
        "hash": content_hash,
        "standings": standings,
        "winners": winners,
        "vote_counts": [],
        "leading_party": standings[0][:80] if standings else ""
    }

def fetch_ecn():
    """Scrape Election Commission Nepal - official results"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get("https://result.election.gov.np/", headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    standings  = []
    vote_counts = []
    winners    = []

    # Tables are most reliable for official sites
    for row in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
        if len(cells) >= 2:
            text = " | ".join(c for c in cells if c)
            if not is_junk(text) and len(text) < 200 and has_number(text):
                if has_party(text):
                    standings.append(text)
                elif re.search(r'\d{3,}', text):
                    vote_counts.append(text)

    standings   = list(dict.fromkeys(standings))[:10]
    vote_counts = list(dict.fromkeys(vote_counts))[:10]

    meaningful   = " ".join(standings + vote_counts)
    content_hash = hashlib.md5(meaningful.encode()).hexdigest()

    return {
        "hash": content_hash,
        "standings": standings,
        "vote_counts": vote_counts,
        "winners": winners,
        "leading_party": standings[0][:80] if standings else ""
    }

def fetch_generic(site):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(site["url"], headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    standings = []
    vote_counts = []
    winners = []
    for row in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
        if len(cells) >= 2:
            text = " | ".join(c for c in cells if c)
            if has_number(text) and not is_junk(text) and "207" not in text and len(text) < 200:
                if has_party(text):
                    standings.append(text)
                elif re.search(r"\d{3,}", text):
                    vote_counts.append(text)
    for tag in soup.find_all(["li","div","p","span"]):
        text = tag.get_text(separator=" ", strip=True)
        if has_party(text) and has_number(text) and not is_junk(text) and "207" not in text and 5 < len(text) < 150:
            standings.append(text)
    standings = list(dict.fromkeys(standings))[:10]
    vote_counts = list(dict.fromkeys(vote_counts))[:10]
    meaningful = " ".join(standings + vote_counts)
    return {
        "hash": hashlib.md5(meaningful.encode()).hexdigest(),
        "standings": standings, "vote_counts": vote_counts,
        "winners": winners, "leading_party": standings[0][:80] if standings else ""
    }

def fetch_site(site):
    if site["type"] == "ekantipur":
        return fetch_ekantipur()
    elif site["type"] == "ecn":
        return fetch_ecn()
    else:
        return fetch_generic(site)

def detect_change_type(old, new):
    new_winners = [w for w in new.get("winners", []) if w not in old.get("winners", [])]
    if new_winners:
        return "win", new_winners
    if old.get("leading_party") and new.get("leading_party"):
        if old["leading_party"] != new["leading_party"]:
            return "lead_change", []
    if old.get("hash") != new.get("hash"):
        return "update", []
    return "none", []

def build_startup_summary(all_states):
    all_standings  = []
    all_counts     = []
    all_winners    = []
    for url, data in all_states.items():
        if data:
            all_standings += data.get("standings", [])
            all_counts    += data.get("vote_counts", [])
            all_winners   += data.get("winners", [])

    all_standings = list(dict.fromkeys(all_standings))
    all_counts    = list(dict.fromkeys(all_counts))
    all_winners   = list(dict.fromkeys(all_winners))

    lines = [
        f"🇳🇵 <b>NEPAL ELECTION 2082 — CURRENT STATUS</b>",
        f"🕐 <i>{now_str()}</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    if all_winners:
        lines.append("🏆 <b>DECLARED WINNERS:</b>")
        for w in all_winners[:5]:
            lines.append(f"    🏅 {w[:180]}")
        lines.append("")

    if all_standings:
        lines.append("📊 <b>PARTY STANDINGS:</b>")
        for s in all_standings[:8]:
            lines.append(f"    • {s[:160]}")
        lines.append("")

    if all_counts:
        lines.append("🗳 <b>LATEST VOTE COUNTS:</b>")
        for c in all_counts[:5]:
            lines.append(f"    • {c[:150]}")
        lines.append("")

    # Filter out any old election data (2074, 2079)
    all_standings = [s for s in all_standings if "207" not in s]
    all_counts    = [c for c in all_counts    if "207" not in c]
    all_winners   = [w for w in all_winners   if "207" not in w]

    if not all_standings and not all_counts and not all_winners:
        lines.append("⏳ <b>Live counting not started yet.</b>")
        lines.append("")
        lines.append("    Polls are open today. The bot will automatically")
        lines.append("    send updates the moment counting begins!")
        lines.append("")

    lines.append("🔗 <b>Live Sources:</b>")
    for site in SITES:
        lines.append(f"    {site['emoji']} <a href='{site['url']}'>{site['name']}</a>")

    return "\n".join(lines)

def build_update(site, data, old_data, change_type, new_winners):
    if change_type == "win":
        lines = [f"🏆 <b>WINNER DECLARED!</b>", f"{site['emoji']} <b>{site['name']}</b>",
                 f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", "", "🎉 <b>Winner(s):</b>"]
        for w in new_winners[:3]: lines.append(f"    🏅 {w[:200]}")
    elif change_type == "lead_change":
        lines = [f"🚨 <b>LEAD CHANGE!</b>", f"{site['emoji']} <b>{site['name']}</b>",
                 f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", "", "⚡ <b>Lead has changed!</b>"]
        if old_data.get("leading_party"): lines.append(f"    <i>Before: {old_data['leading_party'][:120]}</i>")
        if data.get("leading_party"):     lines.append(f"    <b>Now: {data['leading_party'][:120]}</b>")
    else:
        lines = [f"🔔 <b>Vote Count Update</b>", f"{site['emoji']} <b>{site['name']}</b>",
                 f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", ""]

    lines.append("")
    if data.get("vote_counts"):
        lines.append("🗳 <b>Latest Counts:</b>")
        for c in data["vote_counts"][:5]: lines.append(f"    • {c[:150]}")
        lines.append("")
    if data.get("standings"):
        lines.append("📊 <b>Party Standings:</b>")
        for s in data["standings"][:5]: lines.append(f"    • {s[:150]}")
        lines.append("")
    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return

    log(f"Agent started. Interval: {INTERVAL}s")

    send_telegram(
        f"🇳🇵 <b>Nepal Election Alert Bot — Starting up...</b>\n\n"
        f"Fetching latest results from {len(SITES)} sources...\n"
        f"<i>Please wait a moment.</i>"
    )

    site_states = {site["url"]: None for site in SITES}

    for site in SITES:
        try:
            log(f"Startup fetch: {site['name']}...")
            site_states[site["url"]] = fetch_site(site)
            log(f"Done: {site['name']}")
        except Exception as e:
            log(f"Startup error {site['name']}: {e}")
        time.sleep(2)

    send_telegram(build_startup_summary(site_states))
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
                else:
                    change_type, new_winners = detect_change_type(old, data)
                    if change_type != "none":
                        send_telegram(build_update(site, data, old, change_type, new_winners))
                        alerts += 1
                        site_states[url] = data
                        log(f"{change_type.upper()} on {site['name']}!")
                    else:
                        log(f"No change on {site['name']}.")
            except Exception as e:
                log(f"Error {site['name']}: {e}")
            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
