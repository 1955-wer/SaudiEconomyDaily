import json
import hashlib
from pathlib import Path

import feedparser
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES_FILE = BASE_DIR / "config" / "sources.json"

TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = None

def load_sources():
with open(SOURCES_FILE, "r", encoding="utf-8") as f:
data = json.load(f)

```
return [
    source
    for source in data.get("sources", [])
    if source.get("enabled", True)
]
```

def make_id(title, url):
value = f"{title}|{url}".encode("utf-8")
return hashlib.sha256(value).hexdigest()[:16]

def fetch_rss(source):
rss_url = source.get("rss")

```
if not rss_url:
    print(f"No RSS configured: {source.get('name', 'Unknown')}")
    return []

print(f"RSS: {rss_url}")

try:
    response = requests.get(
        rss_url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 SaudiEconomyDaily/1.0"
        }
    )

    print(f"HTTP status: {response.status_code}")

    if response.status_code != 200:
        print(f"RSS request failed: {response.status_code}")
        return []

    feed = feedparser.parse(response.content)

except Exception as e:
    print(f"RSS error: {e}")
    return []

if not feed.entries:
    print("RSS returned no entries")
    return []

articles = []

for entry in feed.entries[:20]:
    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()

    if not title or not link:
        continue

    published = (
        entry.get("published")
        or entry.get("updated")
        or ""
    )

    articles.append({
        "id": make_id(title, link),
        "source": source.get("name", "Unknown"),
        "country": source.get("country", ""),
        "type": source.get("type", ""),
        "priority": source.get("priority", 1),
        "topics": source.get("topics", []),
        "title": title,
        "url": link,
        "published": published
    })

print(f"RSS articles found: {len(articles)}")

return articles
```

def fetch_source(source):
return fetch_rss(source)

def remove_duplicates(articles):
unique = {}

```
for article in articles:
    unique[article["id"]] = article

return list(unique.values())
```

def send_telegram(message):
token = TELEGRAM_BOT_TOKEN
chat_id = TELEGRAM_CHAT_ID

```
if not token or not chat_id:
    print("Telegram credentials are not available")
    return False

url = f"https://api.telegram.org/bot{token}/sendMessage"

try:
    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        },
        timeout=20
    )

    print(f"Telegram HTTP status: {response.status_code}")

    data = response.json()

    if data.get("ok"):
        print("Telegram message sent successfully")
        return True

    print(f"Telegram error: {data}")
    return False

except Exception as e:
    print(f"Telegram send error: {e}")
    return False
```

def format_article(article):
title = article["title"]
source = article["source"]
url = article["url"]

```
return (
    f"🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    f"📰 <b>{title}</b>\n\n"
    f"📌 المصدر: {source}\n"
    f"🔗 <a href=\"{url}\">قراءة الخبر</a>"
)
```

def main():
global TELEGRAM_BOT_TOKEN
global TELEGRAM_CHAT_ID

```
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("=" * 60)
print("🇸🇦 Saudi Economy Daily - News Fetcher")
print("=" * 60)

print()
print("=" * 60)
print("Testing Telegram connection")
print("=" * 60)

test_message = (
    "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    "✅ اتصال Telegram يعمل بنجاح."
)

if send_telegram(test_message):
    print("Telegram test succeeded")
else:
    print("Telegram test failed")

print()
print("=" * 60)
print("Starting news collection")
print("=" * 60)

try:
    sources = load_sources()
except Exception as e:
    print(f"Failed to load sources.json: {e}")
    return

print(f"Enabled sources: {len(sources)}")
print()

all_articles = []

for source in sources:
    name = source.get("name", "Unknown")

    try:
        articles = fetch_source(source)

        if articles:
            print(f"Found {len(articles)} articles: {name}")
            all_articles.extend(articles)
        else:
            print(f"No articles: {name}")

    except Exception as e:
        print(f"Source error - {name}: {e}")

articles = remove_duplicates(all_articles)

articles.sort(
    key=lambda article: article.get("priority", 1),
    reverse=True
)

print()
print("=" * 60)
print(f"Unique articles found: {len(articles)}")
print("=" * 60)

if not articles:
    print("No news articles were found.")
    return

print()
print("Sending news to Telegram...")

sent = 0

for article in articles[:10]:
    print()
    print(f"📰 {article['title']}")
    print(f"📌 {article['source']}")
    print(f"🔗 {article['url']}")

    message = format_article(article)

    if send_telegram(message):
        sent += 1

print()
print("=" * 60)
print(f"News sent to Telegram: {sent}")
print("=" * 60)
```

if **name** == "**main**":
main()
