import json
import hashlib
import os
from pathlib import Path

import feedparser
import requests


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES_FILE = BASE_DIR / "config" / "sources.json"


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        source
        for source in data.get("sources", [])
        if source.get("enabled", True)
    ]


def make_id(title, url):
    value = f"{title}|{url}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def fetch_rss(source):
    rss_url = source.get("rss")

    if not rss_url:
        return []

    feed = feedparser.parse(rss_url)

    if getattr(feed, "bozo", False) and not feed.entries:
        return []

    articles = []

    for entry in feed.entries[:30]:
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

    return articles


def fetch_source(source):
    return fetch_rss(source)


def remove_duplicates(articles):
    unique = {}

    for article in articles:
        unique[article["id"]] = article

    return list(unique.values())


def send_to_telegram(article):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Telegram secrets are missing")
        return False

    message = (
        "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
        f"📰 <b>{article['title']}</b>\n\n"
        f"📌 المصدر: {article['source']}\n"
        f"🔗 <a href=\"{article['url']}\">قراءة الخبر</a>"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        },
        timeout=30
    )

    if response.ok:
        return True

    print(f"❌ Telegram error: {response.text}")
    return False


def main():
    sources = load_sources()

    print("=" * 60)
    print("🇸🇦 Saudi Economy Daily - News Fetcher")
    print("=" * 60)

    print(f"Enabled sources: {len(sources)}")
    print()

    all_articles = []

    for source in sources:
        name = source.get("name", "Unknown")

        try:
            articles = fetch_source(source)

            if articles:
                print(f"✅ {name}: {len(articles)} articles")
                all_articles.extend(articles)
            else:
                print(f"⚪ {name}: no RSS configured")

        except Exception as e:
            print(f"❌ {name}: {e}")

    articles = remove_duplicates(all_articles)

    articles.sort(
        key=lambda article: article.get("priority", 1),
        reverse=True
    )

    print()
    print("=" * 60)
    print(f"Unique articles found: {len(articles)}")
    print("=" * 60)

    # نرسل أول 5 أخبار فقط للاختبار
    test_articles = articles[:5]

    if not test_articles:
        print("⚠️ No articles found")
        return

    print(f"📤 Sending {len(test_articles)} articles to Telegram...")

    sent = 0

    for article in test_articles:
        print()
        print(f"📰 {article['title']}")
        print(f"📌 المصدر: {article['source']}")

        if send_to_telegram(article):
            print("✅ Sent to Telegram")
            sent += 1
        else:
            print("❌ Failed to send")

    print()
    print("=" * 60)
    print(f"Telegram messages sent: {sent}/{len(test_articles)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
