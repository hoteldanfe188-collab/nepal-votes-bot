#!/usr/bin/env python3
"""
Nepal Election - Alert Agent
Only sends: Vote count updates, Lead Changes, Winner Declared, New FB Posts
No spam — only meaningful changes trigger notifications.
"""

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import os
import re
from datetime import datetime
import xml.etree.ElementTree as ET

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

FB_FEEDS = [
    {
        "name": "Indepth Story Nepal",
        "url": "https://rss.app/feed/w4KHF6tv2S1bOmIW",
        "fb_url": "https://www.facebook.com/indepthstorynepal/",
        "emoji": "📰"
    },
    {
        "name": "Routine of Nepal Banda",
        "url": "https://rss.app/feed/K4fcAOe8Q7XRwhCw",
        "fb_url": "https://www.facebook.com/officialroutineofnepalbanda/",
        "emoji": "📢"
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

def extract_vote_numbers(soup):
    """Extract only actual vote count rows — candidate name + numbers"""
    results = []
    # Look for patterns like "Name 12,345 10,234 (leading)"
    for tag in soup.find_all(["tr", "li", "div", "p", "span"]):
        text = tag.get_text(separator=" ", strip=True)
        # Must contain a number with comma or 4+ digits (actual vote count)
        if re.search(r'\d{1,3},\d{3}', text) or re.search(r'\d{4,}', text):
            # Skip navigation / menu junk
            if any(bad in text.lower() for bad in ["प्रतिनिधिसभा प्रदेश कोशी प्रदेश मधेस", "cookie", "copyright", "menu", "login", "register"]):
                continue
            # Must be reasonably short and meaningful
            if 5 < len(text) < 180:
                results.append(text)
    return results[:10]

def extract_party_standings(soup):
    """Extract party-level totals — won + leading counts"""
    standings = []
    for tag in soup.find_all(["tr", "div", "li"]):
        text = tag.get_text(separator=" ", strip=True)
        # Look for party names with seat counts
        if re.search(r'\d+', text) and any(k in text.lower() for k in [
            "uml", "nc", "rpp", "माओवादी", "एमाले", "कांग्रेस",
            "rastriya", "janajati", "party", "पार्टी", "दल",
            "won", "leading", "जित", "अगाडि", "seats", "सिट"
        ]):
            if 5 < len(text) < 150:
                standings.append(text)
    return standings[:8]

def extract_winners(soup):
    """Extract winner declarations"""
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

    vote_counts  = extract_vote_numbers(soup)
    standings    = extract_party_standings(soup)
    winners      = extract_winners(soup)
    leading_party = standings[0][:80] if standings else ""

    # Hash only the meaningful numbers, not the whole page
    meaningful = " ".join(vote_counts + standings)
    content_hash = hashlib.md5(meaningful.encode()).hexdigest()

    return {
        "hash": content_hash,
        "vote_counts": vote_counts,
        "standings": standings,
        "winners": winners,
        "leading_party": leading_party,
    }

def detect_change_type(old, new):
    # Winner check (highest priority)
    new_winners = [w for w in new.get("winners", []) if w not in old.get("winners", [])]
    if new_winners:
        return "win", new_winners
    # Lead change
    if old.get("leading_party") and new.get("leading_party"):
        if old["leading_party"] != new["leading_party"]:
            return "lead_change", []
    # Vote count update
    if old.get("vote_counts") != new.get("vote_counts"):
        return "update", []
    return "none", []

# ── Message builders ───────────────────────────────────────────────────────
def build_regular_update(site, data, old_data):
    new_counts = [c for c in data["vote_counts"] if c not in old_data.get("vote_counts", [])]
    show_counts = new_counts[:5] if new_counts else data["vote_counts"][:5]

    lines = []
    lines.append(f"🔔 <b>Vote Count Update</b>")
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    if show_counts:
        lines.append(f"🗳 <b>Latest Vote Counts:</b>")
        for c in show_counts:
            lines.append(f"    • {c[:150]}")
        lines.append("")

    if data["standings"]:
        lines.append(f"📊 <b>Party Standings:</b>")
        for s in data["standings"][:5]:
            lines.append(f"    • {s[:150]}")
        lines.append("")

    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_lead_change(site, data, old_data):
    lines = []
    lines.append(f"🚨 <b>LEAD CHANGE!</b>")
    lines.append(f"{site['emoji']} <b>{site['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"⚡ <b>The lead has changed!</b>")
    if old_data.get("leading_party"):
        lines.append(f"    <i>Before: {old_data['leading_party'][:120]}</i>")
    if data.get("leading_party"):
        lines.append(f"    <b>Now: {data['leading_party'][:120]}</b>")
    lines.append("")

    if data["vote_counts"]:
        lines.append(f"🗳 <b>Latest Counts:</b>")
        for c in data["vote_counts"][:5]:
            lines.append(f"    • {c[:150]}")
        lines.append("")

    if data["standings"]:
        lines.append(f"📊 <b>Current Standings:</b>")
        for s in data["standings"][:5]:
            lines.append(f"    • {s[:150]}")
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
    lines.append(f"🎉 <b>Winner(s):</b>")
    for w in new_winners[:3]:
        lines.append(f"    🏅 {w[:200]}")
    lines.append("")

    if data["standings"]:
        lines.append(f"📊 <b>Overall Tally:</b>")
        for s in data["standings"][:5]:
            lines.append(f"    • {s[:150]}")
        lines.append("")

    lines.append(f"🔗 <a href='{site['url']}'>View Full Results →</a>")
    return "\n".join(lines)

def build_fb_post(feed, post):
    lines = []
    lines.append(f"📣 <b>New Post — {feed['name']}</b>")
    lines.append(f"{feed['emoji']} <b>{feed['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if post["title"]:
        lines.append(f"📌 <b>{post['title'][:200]}</b>")
        lines.append("")
    if post["description"]:
        lines.append(f"<i>{post['description'][:300]}</i>")
        lines.append("")
    if post["link"]:
        lines.append(f"🔗 <a href='{post['link']}'>Read Full Post →</a>")
    return "\n".join(lines)

def fetch_rss(feed):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(feed["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link  = item.findtext("link", "").strip()
        desc  = item.findtext("description", "").strip()
        guid  = item.findtext("guid", link).strip()
        if desc:
            desc = BeautifulSoup(desc, "html.parser").get_text(separator=" ", strip=True)[:300]
        items.append({"guid": guid, "title": title[:200], "link": link, "description": desc})
    return items[:10]

# ── Main agent ─────────────────────────────────────────────────────────────
def run_agent():
    if not TOKEN or not CHAT_ID:
        log("ERROR: TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set!")
        return

    log(f"Agent started. Checking every {INTERVAL}s.")

    sites_list = "\n".join([f"{s['emoji']} <b>{s['name']}</b>" for s in SITES])
    fb_list    = "\n".join([f"{f['emoji']} <b>{f['name']}</b>" for f in FB_FEEDS])

    send_telegram(
        f"🇳🇵 <b>Nepal Election Alert Agent — Live!</b>\n\n"
        f"📊 <b>Election Sites:</b>\n{sites_list}\n\n"
        f"📣 <b>Facebook Pages:</b>\n{fb_list}\n\n"
        f"⏱ <i>Checking every {INTERVAL} seconds</i>\n\n"
        f"You'll be notified on:\n"
        f"    🔔 Vote count updates\n"
        f"    🚨 Lead changes\n"
        f"    🏆 Winners declared\n"
        f"    📣 New Facebook posts\n\n"
        f"<i>Stay tuned!</i>"
    )

    site_states = {site["url"]: None for site in SITES}
    fb_seen     = {feed["url"]: set() for feed in FB_FEEDS}
    checks = 0
    alerts = 0

    while True:
        # Election sites
        for site in SITES:
            try:
                log(f"Checking {site['name']}...")
                data = fetch_site(site)
                url  = site["url"]
                checks += 1

                if site_states[url] is None:
                    site_states[url] = data
                    log(f"Baseline for {site['name']} captured.")

                else:
                    change_type, new_winners = detect_change_type(site_states[url], data)

                    if change_type == "win":
                        send_telegram(build_winner_declared(site, data, new_winners))
                        alerts += 1
                        log(f"WINNER on {site['name']}!")
                        site_states[url] = data

                    elif change_type == "lead_change":
                        send_telegram(build_lead_change(site, data, site_states[url]))
                        alerts += 1
                        log(f"LEAD CHANGE on {site['name']}!")
                        site_states[url] = data

                    elif change_type == "update":
                        send_telegram(build_regular_update(site, data, site_states[url]))
                        alerts += 1
                        log(f"COUNT UPDATE on {site['name']}.")
                        site_states[url] = data

                    else:
                        log(f"No meaningful change on {site['name']}.")

            except Exception as e:
                log(f"Error on {site['name']}: {e}")

            time.sleep(3)

        # Facebook RSS
        for feed in FB_FEEDS:
            try:
                log(f"Checking FB: {feed['name']}...")
                posts = fetch_rss(feed)

                if not fb_seen[feed["url"]]:
                    fb_seen[feed["url"]] = {p["guid"] for p in posts}
                    log(f"FB baseline for {feed['name']}: {len(posts)} posts.")
                else:
                    for post in posts:
                        if post["guid"] not in fb_seen[feed["url"]]:
                            send_telegram(build_fb_post(feed, post))
                            fb_seen[feed["url"]].add(post["guid"])
                            alerts += 1
                            log(f"NEW FB POST from {feed['name']}!")

            except Exception as e:
                log(f"Error on FB {feed['name']}: {e}")

            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
