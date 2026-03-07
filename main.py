#!/usr/bin/env python3
"""
Nepal Election - Alert Agent
Monitors election sites + Facebook RSS + sends images from FB posts
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
    },
    {
        "name": "Election Commission Nepal",
        "url": "https://result.election.gov.np/",
        "emoji": "🏛"
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

def send_telegram_photo(image_url, caption):
    """Send a photo with caption to Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    try:
        if len(caption) > 1024:
            caption = caption[:1020] + "..."
        resp = requests.post(url, json={
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }, timeout=15)
        if resp.status_code == 200:
            log("Telegram photo sent!")
        else:
            # Fall back to text if photo fails
            log(f"Photo send failed ({resp.status_code}), sending as text.")
            send_telegram(caption)
    except Exception as e:
        log(f"Photo error: {e}")
        send_telegram(caption)

def extract_vote_numbers(soup):
    results = []
    for tag in soup.find_all(["tr", "li", "div", "p", "span"]):
        text = tag.get_text(separator=" ", strip=True)
        if re.search(r'\d{1,3},\d{3}', text) or re.search(r'\d{4,}', text):
            if any(bad in text.lower() for bad in [
                "प्रतिनिधिसभा प्रदेश कोशी प्रदेश मधेस",
                "cookie", "copyright", "menu", "login", "register", "admission"
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
            "uml", "nc", "rpp", "माओवादी", "एमाले", "कांग्रेस",
            "rastriya", "party", "पार्टी", "दल",
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

    meaningful   = " ".join(vote_counts + standings)
    content_hash = hashlib.md5(meaningful.encode()).hexdigest()

    return {
        "hash": content_hash,
        "vote_counts": vote_counts,
        "standings": standings,
        "winners": winners,
        "leading_party": leading_party,
    }

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

        # Extract image from description or enclosure
        image_url = ""
        enclosure = item.find("enclosure")
        if enclosure is not None:
            image_url = enclosure.get("url", "")

        # Also try to find image in description HTML
        if not image_url and desc:
            desc_soup = BeautifulSoup(desc, "html.parser")
            img = desc_soup.find("img")
            if img:
                image_url = img.get("src", "")
            desc = desc_soup.get_text(separator=" ", strip=True)[:300]

        items.append({
            "guid": guid,
            "title": title[:200],
            "link": link,
            "description": desc,
            "image_url": image_url
        })
    return items[:10]

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

def build_regular_update(site, data, old_data):
    new_counts  = [c for c in data["vote_counts"] if c not in old_data.get("vote_counts", [])]
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

def build_fb_caption(feed, post):
    lines = []
    lines.append(f"📣 <b>{feed['name']}</b>")
    lines.append(f"🕐 <i>{now_str()}</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    if post["title"]:
        lines.append(f"📌 <b>{post['title'][:200]}</b>")
        lines.append("")
    if post["description"] and post["description"] != post["title"]:
        lines.append(f"<i>{post['description'][:300]}</i>")
        lines.append("")
    if post["link"]:
        lines.append(f"🔗 <a href='{post['link']}'>View Full Post →</a>")
    return "\n".join(lines)

def send_sample_notifications():
    """Send sample notifications on startup"""
    log("Sending sample notifications...")

    # Sample win
    send_telegram(
        f"🏆 <b>WINNER DECLARED!</b>\n"
        f"🗳 <b>Nepal Votes Live</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎉 <b>Winner(s):</b>\n"
        f"    🏅 Balen Shah (Independent) elected from Jhapa-5!\n"
        f"    Final votes: 39,284 | Margin: 28,991\n\n"
        f"📊 <b>Overall Tally:</b>\n"
        f"    • CPN-UML: 67 seats\n"
        f"    • NC: 54 seats\n"
        f"    • RPP: 21 seats\n"
        f"    • Independent: 12 seats\n\n"
        f"🔗 <a href='https://nepalvotes.live'>View Full Results →</a>"
    )
    time.sleep(2)

    # Sample count update
    send_telegram(
        f"🔔 <b>Vote Count Update</b>\n"
        f"🏛 <b>Election Commission Nepal</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🗳 <b>Latest Vote Counts:</b>\n"
        f"    • Jhapa-5: Balen Shah 39,284 | KP Oli 10,293\n"
        f"    • Kathmandu-3: Ram Thapa 12,450 | Sita Rai 10,110\n"
        f"    • Lalitpur-2: Hari KC 8,900 | Mina Lama 8,450\n\n"
        f"📊 <b>Party Standings:</b>\n"
        f"    • CPN-UML: 67 leading\n"
        f"    • NC: 54 leading\n"
        f"    • RPP: 21 leading\n\n"
        f"🔗 <a href='https://result.election.gov.np/'>View Full Results →</a>"
    )
    log("Sample notifications sent!")

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
        f"Notifications:\n"
        f"    🔔 Vote count updates\n"
        f"    🚨 Lead changes\n"
        f"    🏆 Winners declared\n"
        f"    📣 New Facebook posts (with images)\n\n"
        f"<i>Stay tuned!</i>"
    )

    # Send samples on startup
    send_sample_notifications()

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

        # Facebook RSS with images
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
                            caption = build_fb_caption(feed, post)
                            if post.get("image_url"):
                                send_telegram_photo(post["image_url"], caption)
                            else:
                                send_telegram(caption)
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
