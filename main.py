#!/usr/bin/env python3
"""
Nepal Election - Advanced Alert Agent
Monitors election sites + Facebook pages via RSS
Three notification types: Regular Update, Lead Change, Winner Declared + New FB Post
Deployed on Railway.app — runs 24/7
"""

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import os
from datetime import datetime
import xml.etree.ElementTree as ET

TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = int(os.environ.get("INTERVAL", "60"))

# Election websites
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

# Facebook pages via RSS
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

# ── Election site fetching ─────────────────────────────────────────────────
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

    leading_party = parties[0][:80] if parties else ""
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

# ── Facebook RSS fetching ──────────────────────────────────────────────────
def fetch_rss(feed):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(feed["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    items = []
    ns = ""
    for item in root.findall(f".//item"):
        title = item.findtext("title", "").strip()
        link  = item.findtext("link", "").strip()
        desc  = item.findtext("description", "").strip()
        pub   = item.findtext("pubDate", "").strip()
        guid  = item.findtext("guid", link).strip()

        # Clean HTML from description
        if desc:
            desc_soup = BeautifulSoup(desc, "html.parser")
            desc = desc_soup.get_text(separator=" ", strip=True)[:300]

        items.append({
            "guid": guid,
            "title": title[:200],
            "link": link,
            "description": desc,
            "pubDate": pub
        })

    return items[:10]  # latest 10 posts

# ── Change detection ───────────────────────────────────────────────────────
def detect_change_type(old, new):
    new_winners = [w for w in new.get("winners", []) if w not in old.get("winners", [])]
    if new_winners:
        return "win", new_winners
    if old.get("leading_party") and new.get("leading_party"):
        if old["leading_party"] != new["leading_party"]:
            return "lead_change", []
    return "update", []

# ── Message builders ───────────────────────────────────────────────────────
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
        f"Notification types:\n"
        f"    🔔 Regular count updates\n"
        f"    🚨 Lead change alerts\n"
        f"    🏆 Winner declared alerts\n"
        f"    📣 New Facebook posts\n\n"
        f"<i>Stay tuned for live updates!</i>"
    )

    # State trackers
    site_states = {site["url"]: None for site in SITES}
    fb_seen     = {feed["url"]: set() for feed in FB_FEEDS}

    checks = 0
    alerts = 0

    while True:
        # ── Check election sites ───────────────────────────────────────────
        for site in SITES:
            try:
                log(f"Checking {site['name']}...")
                data = fetch_site(site)
                url  = site["url"]
                checks += 1

                if site_states[url] is None:
                    site_states[url] = data
                    log(f"Baseline for {site['name']} captured.")
                    send_telegram(build_regular_update(site, data, {}))

                elif data["hash"] != site_states[url]["hash"]:
                    alerts += 1
                    change_type, new_winners = detect_change_type(site_states[url], data)

                    if change_type == "win":
                        send_telegram(build_winner_declared(site, data, new_winners))
                        log(f"WINNER on {site['name']}!")
                    elif change_type == "lead_change":
                        send_telegram(build_lead_change(site, data, site_states[url]))
                        log(f"LEAD CHANGE on {site['name']}!")
                    else:
                        send_telegram(build_regular_update(site, data, site_states[url]))
                        log(f"UPDATE on {site['name']}.")

                    site_states[url] = data
                else:
                    log(f"No changes on {site['name']}.")

            except Exception as e:
                log(f"Error on {site['name']}: {e}")

            time.sleep(3)

        # ── Check Facebook RSS feeds ───────────────────────────────────────
        for feed in FB_FEEDS:
            try:
                log(f"Checking FB: {feed['name']}...")
                posts = fetch_rss(feed)

                if not fb_seen[feed["url"]]:
                    # First run — just save all current post IDs as baseline
                    fb_seen[feed["url"]] = {p["guid"] for p in posts}
                    log(f"FB baseline for {feed['name']}: {len(posts)} posts.")
                else:
                    for post in posts:
                        if post["guid"] not in fb_seen[feed["url"]]:
                            # New post!
                            alerts += 1
                            send_telegram(build_fb_post(feed, post))
                            fb_seen[feed["url"]].add(post["guid"])
                            log(f"NEW FB POST from {feed['name']}!")

            except Exception as e:
                log(f"Error on FB {feed['name']}: {e}")

            time.sleep(3)

        log(f"Checks: {checks} | Alerts: {alerts} | Next in {INTERVAL}s")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_agent()
