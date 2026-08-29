import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import feedparser

BASE_DIR = Path(**file**).resolve().parent.parent
SOURCES_FILE = BASE_DIR / "config" / "sources.json"
DATA_DIR = BASE_DIR / "data"
NEWS_FILE = DATA_DIR / "news.json"

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

def save_articles(articles):
DATA_DIR.mkdir(parents=True, exist_ok=True)

```
data = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "count": len(articles),
    "articles": articles
}

with open(NEWS_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"💾 Saved to: {NEWS_FILE}")
```

def main():
sources = load_sources()

```
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
            if source.get("rss"):
                print(f"⚪ {name}: RSS returned no articles")
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
print(f"📰 Unique articles found: {len(articles)}")
print("=" * 60)

save_articles(articles)

for article in articles[:20]:
    print()
    print(f"📰 {article['title']}")
    print(f"📌 المصدر: {article['source']}")
    print(f"🔗 {article['url']}")
```

if **name** == "**main**":
main()
