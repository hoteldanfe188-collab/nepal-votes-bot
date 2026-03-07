#!/usr/bin/env python3
"""
Nepal Election - Alert Agent
Fixed RSS parsing with lxml + image support
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
    {"name": "Election Commission", "url": "https://result.election.gov.np/",                        "emoji": "🏛"}
]

FB_FEEDS = [
    {"name": "Indepth Story Nepal",    "url": "https://rss.app/feed/w4KHF6tv2S1bOmIW", "emoji": "📰"},
    {"name": "Routine of Nepal Banda", "url": "https://rss.app/feed/K4fcAOe8Q7XRwhCw", "emoji": "📢"}
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
            log(f"Photo failed, sending as text.")
            send_telegram(caption)
    except Exception as e:
        log(f"Photo error: {e}")
        send_telegram(caption)

def fetch_rss(feed):
    """Fetch RSS using BeautifulSoup with lxml for robust XML parsing"""
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(feed["url"], headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml-xml")
    items = []

    for item in soup.find_all("item"):
        title     = item.find("title")
        link      = item.find("link")
        desc      = item.find("description")
        guid      = item.find("guid")
        enclosure = item.find("enclosure")

        title_text = title.get_text(strip=True) if title else ""
        link_text  = link.get_text(strip=True) if link else ""
        guid_text  = guid.get_text(strip=True) if guid else link_text
        desc_text  = ""
        image_url  = ""

        if enclosure:
            image_url = enclosure.get("url", "")

        if desc:
            raw_desc  = desc.get_text()
            desc_soup = BeautifulSoup(raw_desc, "html.parser")
            img = desc_soup.find("img")
            if img and not image_url:
                image_url = img.get("src", "")
            desc_text = desc_soup.get_text(separator=" ", strip=True)[:300]

        items.append({
            "guid":        guid_text[:300],
            "title":       title_text[:200],
            "link":        link_text,
            "description": desc_text,
            "image_url":   image_url
        })

    return items[:10]

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
    meaningful    = " ".join(vote_counts + standings)
    content_hash  = hashlib.md5(meaningful.encode()).hexdigest()

    return {
        "hash":          content_hash,
        "vote_counts":   vote_counts,
        "standings":     standings,
        "winners":       winners,
        "leading_party": leading_party,
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

def build_fb_caption(feed, post):
    lines = [f"📣 <b>{feed['name']}</b>", f"🕐 <i>{now_str()}</i>", "━━━━━━━━━━━━━━━━━━━━━━", ""]
    if post["title"]: lines.append(f"📌 <b>{post['title'][:200]}</b>"); lines.append("")
    if post["description"] and post["description"] != post["title"]:
        lines.append(f"<i>{post['description'][:300]}</i>"); lines.append("")
    if post["link"]: lines.append(f"🔗 <a href='{post['link']}'>View Full Post →</a>")
    return "\n".join(lines)

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

    # Sample notifications
    time.sleep(2)
    send_telegram(
        f"🏆 <b>WINNER DECLARED! [SAMPLE]</b>\n"
        f"🗳 <b>Nepal Votes Live</b>\n"
        f"🕐 <i>{now_str()}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎉 <b>Winner(s):</b>\n"
        f"    🏅 Balen Shah (Independent) elected from Jhapa-5!\n"
        f"    Final votes: 39,284 | Margin: 28,991\n\n"
        f"📊 <b>Overall Tally:</b>\n"
        f"    • CPN-UML: 67 seats\n"
        f"    • NC: 54 seats\n"
        f"    • RPP: 21 seats\n\n"
        f"🔗 <a href='https://nepalvotes.live'>View Full Results →</a>"
    )
    time.sleep(2)
    send_telegram(
        f"🔔 <b>Vote Count Update [SAMPLE]</b>\n"
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

    site_states = {site["url"]: None for site in SITES}
    fb_seen     = {feed["url"]: set() for feed in FB_FEEDS}
    checks = 0
    alerts = 0

    while True:
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
                        alerts += 1; site_states[url] = data
                    elif change_type == "lead_change":
                        send_telegram(build_lead_change(site, data, site_states[url]))
                        alerts += 1; site_states[url] = data
                    elif change_type == "update":
                        send_telegram(build_regular_update(site, data, site_states[url]))
                        alerts += 1; site_states[url] = data
                    else:
                        log(f"No meaningful change on {site['name']}.")
            except Exception as e:
                log(f"Error on {site['name']}: {e}")
            time.sleep(3)

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
