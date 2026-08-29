import json
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests

BASE_DIR = Path(**file**).resolve().parent.parent
SOURCES_FILE = BASE_DIR / "config" / "sources.json"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
"User-Agent": (
"Mozilla/5.0 (X11; Linux x86_64) "
"AppleWebKit/537.36 Chrome/120 Safari/537.36"
)
}

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

def clean_text(text):
if not text:
return ""

```
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"\s+", " ", text)

return text.strip()
```

def fetch_rss(source, rss_url):
print(f"RSS: {rss_url}")

```
try:
    response = requests.get(
        rss_url,
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    feed = feedparser.parse(response.content)

except Exception as e:
    print(f"RSS error: {e}")
    return []

if not feed.entries:
    print("RSS returned no entries")
    return []

articles = []

for entry in feed.entries[:30]:

    title = clean_text(entry.get("title", ""))
    link = entry.get("link", "").strip()

    if not title or not link:
        continue

    published = (
        entry.get("published")
        or entry.get("updated")
        or entry.get("created")
        or ""
    )

    summary = clean_text(
        entry.get("summary", "")
        or entry.get("description", "")
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
        "published": published,
        "summary": summary
    })

return articles
```

def fetch_google_news(source):
"""
يستخدم Google News RSS للبحث عن أخبار المصدر
عندما لا يتوفر RSS مباشر.
"""

```
name = source.get("name", "")
country = source.get("country", "")

query = f'"{name}" السعودية'

if country != "SA":
    query = f'"{name}" السعودية اقتصاد'

google_url = (
    "https://news.google.com/rss/search?"
    f"q={quote(query)}"
    "&hl=ar&gl=SA&ceid=SA:ar"
)

print(f"Google News RSS: {name}")

return fetch_rss(source, google_url)
```

def fetch_source(source):
rss_url = source.get("rss")

```
if rss_url:
    articles = fetch_rss(source, rss_url)

    if articles:
        return articles

return fetch_google_news(source)
```

def remove_duplicates(articles):
unique = {}

```
for article in articles:
    article_id = article["id"]

    if article_id not in unique:
        unique[article_id] = article

return list(unique.values())
```

def is_relevant(article):
text = (
article.get("title", "")
+ " "
+ article.get("summary", "")
).lower()

```
keywords = [
    "السعودية",
    "السعودي",
    "السعودية",
    "riyadh",
    "saudi",
    "saudi arabia",
    "aramco",
    "أرامكو",
    "الاقتصاد",
    "اقتصاد",
    "اقتصادية",
    "الاقتصادي",
    "استثمار",
    "استثمارات",
    "سوق",
    "الأسهم",
    "تاسي",
    "النفط",
    "الطاقة",
    "المالية",
    "البنك المركزي",
    "ساما",
    "ميزانية",
    "وزارة المالية",
    "الشركات",
    "العقار",
    "العقارات",
    "التوظيف",
    "العمل",
    "رؤية 2030",
    "نيوم",
    "نيوم",
    "صندوق الاستثمارات العامة",
    "pif",
    "oil",
    "investment",
    "economy",
    "markets"
]

return any(keyword in text for keyword in keywords)
```

def send_telegram(message):
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
print("Telegram secrets are missing")
return False

```
url = (
    f"https://api.telegram.org/bot"
    f"{TELEGRAM_BOT_TOKEN}/sendMessage"
)

payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": False
}

try:
    response = requests.post(
        url,
        json=payload,
        timeout=20
    )

    print(f"Telegram status: {response.status_code}")
    print(f"Telegram response: {response.text}")

    return response.ok

except Exception as e:
    print(f"Telegram error: {e}")
    return False
```

def format_article(article):
title = article["title"]
source = article["source"]
url = article["url"]

```
published = article.get("published", "")

message = (
    "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    f"📰 <b>{title}</b>\n\n"
    f"📌 المصدر: {source}\n"
)

if published:
    message += f"🕐 {published}\n"

message += f"\n🔗 <a href=\"{url}\">قراءة الخبر</a>"

return message
```

def test_telegram():
print("=" * 60)
print("Testing Telegram connection")
print("=" * 60)

```
test_message = (
    "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
    "✅ اتصال Telegram يعمل بنجاح."
)

success = send_telegram(test_message)

if success:
    print("Telegram test succeeded")
else:
    print("Telegram test failed")

return success
```

def main():

```
print("=" * 60)
print("🇸🇦 Saudi Economy Daily - News Fetcher")
print("=" * 60)

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ Telegram secrets are missing")
    return

# اختبار Telegram
test_telegram()

print()
print("=" * 60)
print("Starting news collection")
print("=" * 60)

sources = load_sources()

print(f"Enabled sources: {len(sources)}")
print()

all_articles = []

for source in sources:

    name = source.get("name", "Unknown")

    try:
        articles = fetch_source(source)

        if articles:
            relevant = [
                article
                for article in articles
                if is_relevant(article)
            ]

            if relevant:
                print(
                    f"✅ {name}: "
                    f"{len(relevant)} relevant articles"
                )

                all_articles.extend(relevant)

            else:
                print(
                    f"⚪ {name}: "
                    f"articles found but none relevant"
                )

        else:
            print(f"⚪ {name}: no articles")

    except Exception as e:
        print(f"❌ {name}: {e}")

articles = remove_duplicates(all_articles)

articles.sort(
    key=lambda article: article.get("priority", 1),
    reverse=True
)

print()
print("=" * 60)
print(f"Unique relevant articles found: {len(articles)}")
print("=" * 60)

if not articles:
    print("No news articles were found.")
    return

# إرسال أول 10 أخبار فقط في الاختبار
sent = 0

for article in articles[:10]:

    print()
    print(f"📰 {article['title']}")
    print(f"📌 المصدر: {article['source']}")
    print(f"🔗 {article['url']}")

    message = format_article(article)

    if send_telegram(message):
        sent += 1
        print("✅ Sent to Telegram")

    else:
        print("❌ Failed to send")

print()
print("=" * 60)
print(f"Telegram articles sent: {sent}")
print("=" * 60)
```

if **name** == "**main**":
main()
