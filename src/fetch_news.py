import json
import hashlib
from datetime import datetime, timezone
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


def fetch_source(source):
    url = source.get("rss") or source.get("url")

    if not url:
        return []

    feed = feedparser.parse(url)

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
            "priority": source.get("priority", 1),
            "title": title,
            "url": link,
            "published": published
        })

    return articles


def main():
    sources = load_sources()

    all_articles = []

    for source in sources:
        try:
            articles = fetch_source(source)
            all_articles.extend(articles)

            print(
                f"[OK] {source.get('name')}: "
                f"{len(articles)} articles"
            )

        except Exception as e:
            print(
                f"[ERROR] {source.get('name')}: {e}"
            )

    # إزالة التكرار
    unique = {}

    for article in all_articles:
        unique[article["id"]] = article

    articles = list(unique.values())

    # الأعلى أولوية أولًا
    articles.sort(
        key=lambda x: x.get("priority", 1),
        reverse=True
    )

    print()
    print(f"Total unique articles: {len(articles)}")

    for article in articles[:10]:
        print()
        print(article["title"])
        print(article["source"])
        print(article["url"])


if __name__ == "__main__":
    main()
