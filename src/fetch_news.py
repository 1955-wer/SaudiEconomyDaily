import json
import hashlib
import os
from pathlib import Path

import feedparser
import requests

SOURCES_FILE = Path("config") / "sources.json"

def load_sources():
with open(SOURCES_FILE, "r", encoding="utf-8") as f:
data = json.load(f)

```
sources = data.get("sources", [])

return [
    source
    for source in sources
    if source.get("enabled", True)
]
```

def make_id(title, url):
text = title + "|" + url
return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def fetch_rss(source):
name = source.get("name", "Unknown")
rss_url = source.get("rss")

```
if not rss_url:
    print("No RSS configured: " + name)
    return []

print("RSS: " + rss_url)

try:
    response = requests.get(
        rss_url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    print("HTTP status: " + str(response.status_code))

    if response.status_code != 200:
        return []

    feed = feedparser.parse(response.content)

except Exception as error:
    print("RSS error: " + str(error))
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

    published = entry.get("published", "")
    if not published:
        published = entry.get("updated", "")

    article = {
        "id": make_id(title, link),
        "source": name,
        "country": source.get("country", ""),
        "type": source.get("type", ""),
        "priority": source.get("priority", 1),
        "topics": source.get("topics", []),
        "title": title,
        "url": link,
        "published": published
    }

    articles.append(article)

print("RSS articles found: " + str(len(articles)))

return articles
```

def remove_duplicates(articles):
unique = {}

```
for article in articles:
    unique[article["id"]] = article

return list(unique.values())
```

def send_telegram(message):
token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

```
if not token:
    print("ERROR: TELEGRAM_BOT_TOKEN is missing")
    return False

if not chat_id:
    print("ERROR: TELEGRAM_CHAT_ID is missing")
    return False

api_url = "https://api.telegram.org/bot" + token + "/sendMessage"

payload = {
    "chat_id": chat_id,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": False
}

try:
    response = requests.post(
        api_url,
        json=payload,
        timeout=20
    )

    print("Telegram HTTP status: " + str(response.status_code))

    data = response.json()

    if data.get("ok"):
        print("Telegram message sent successfully")
        return True

    print("Telegram error: " + str(data))
    return False

except Exception as error:
    print("Telegram error: " + str(error))
    return False
```

def format_article(article):
title = article["title"]
source = article["source"]
url = article["url"]

```
message = (
    "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    "📰 <b>" + title + "</b>\n\n"
    "📌 المصدر: " + source + "\n"
    "🔗 <a href=\"" + url + "\">قراءة الخبر</a>"
)

return message
```

def main():
print("=" * 60)
print("Saudi Economy Daily - News Fetcher")
print("=" * 60)

```
print()
print("Testing Telegram connection")
print("=" * 60)

test_message = (
    "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    "✅ اتصال Telegram يعمل بنجاح."
)

telegram_ok = send_telegram(test_message)

if telegram_ok:
    print("Telegram test succeeded")
else:
    print("Telegram test failed")

print()
print("=" * 60)
print("Starting news collection")
print("=" * 60)

try:
    sources = load_sources()
except Exception as error:
    print("ERROR loading sources.json: " + str(error))
    return

print("Enabled sources: " + str(len(sources)))
print()

all_articles = []

for source in sources:
    name = source.get("name", "Unknown")

    try:
        articles = fetch_rss(source)

        if articles:
            all_articles.extend(articles)
            print("Found articles: " + name)
        else:
            print("No articles: " + name)

    except Exception as error:
        print(
            "Source error - "
            + name
            + ": "
            + str(error)
        )

articles = remove_duplicates(all_articles)

articles.sort(
    key=lambda article: article.get("priority", 1),
    reverse=True
)

print()
print("=" * 60)
print(
    "Unique articles found: "
    + str(len(articles))
)
print("=" * 60)

if not articles:
    print("No news articles were found.")
    return

print()
print("Sending news to Telegram")
print("=" * 60)

sent = 0

for article in articles[:10]:
    print("Sending: " + article["title"])

    message = format_article(article)

    if send_telegram(message):
        sent += 1

print()
print("=" * 60)
print(
    "News sent to Telegram: "
    + str(sent)
)
print("=" * 60)
```

if **name** == "**main**":
main()
