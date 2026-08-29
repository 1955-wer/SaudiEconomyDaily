import json
import hashlib
from pathlib import Path

import feedparser


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
    """
    في هذه المرحلة نجلب المصادر التي تحتوي على RSS فقط.
    المواقع التي لا تحتوي RSS سنضيف لها طرق جلب خاصة لاحقًا.
    """
    return fetch_rss(source)


def remove_duplicates(articles):
    unique = {}

    for article in articles:
        unique[article["id"]] = article

    return list(unique.values())


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

    for article in articles[:20]:
        print()
        print(f"📰 {article['title']}")
        print(f"📌 المصدر: {article['source']}")
        print(f"🔗 {article['url']}")


if __name__ == "__main__":
    main()
