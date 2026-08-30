import os
import json
import hashlib
import requests
import feedparser
from urllib.parse import quote

# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCES_FILE = "config/sources.json"

MAX_ARTICLES_PER_SOURCE = 3
REQUEST_TIMEOUT = 20

# ============================================================
# Helpers
# ============================================================

def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        source
        for source in data.get("sources", [])
        if source.get("enabled", True)
    ]


def make_google_news_url(query):
    encoded_query = quote(query)

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}"
        "&hl=ar"
        "&gl=SA"
        "&ceid=SA:ar"
    )


def clean_text(text):
    if not text:
        return ""

    return " ".join(str(text).split()).strip()


def article_id(title, url):
    value = clean_text(title) + "|" + clean_text(url)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_feed(url):
    try:
        print(f"    Trying RSS: {url}")

        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent": "Mozilla/5.0 SaudiEconomyDaily/1.0"
            }
        )

        if feed.bozo:
            print("    RSS warning: feed.bozo=True")

        if not feed.entries:
            print("    RSS result: 0 entries")
            return []

        print(f"    RSS result: {len(feed.entries)} entries")

        return feed.entries

    except Exception as e:
        print(f"    RSS ERROR: {e}")
        return []


def extract_articles(entries, source):
    articles = []

    for entry in entries[:MAX_ARTICLES_PER_SOURCE]:
        title = clean_text(entry.get("title", ""))
        url = clean_text(entry.get("link", ""))

        if not title or not url:
            continue

        articles.append({
            "id": article_id(title, url),
            "title": title,
            "url": url,
            "source": source.get("name", "مصدر غير معروف"),
            "priority": source.get("priority", 1)
        })

    return articles


# ============================================================
# Source fetching
# ============================================================

def fetch_source(source):
    name = source.get("name", "Unknown")
    methods = source.get("methods", [])

    # Support old format:
    # "rss": "https://example.com/feed"
    if source.get("rss"):
        methods.insert(
            0,
            {
                "type": "rss",
                "url": source["rss"]
            }
        )

    print("")
    print("=" * 60)
    print(f"SOURCE: {name}")
    print("=" * 60)

    # --------------------------------------------------------
    # Method 1: Direct RSS
    # --------------------------------------------------------

    for method in methods:

        method_type = method.get("type")

        if method_type == "rss":
            rss_url = method.get("url")

            if not rss_url:
                continue

            entries = get_feed(rss_url)

            if entries:
                print(f"    SUCCESS: {name} via RSS")

                return extract_articles(entries, source)

    # --------------------------------------------------------
    # Method 2: Google News RSS
    # --------------------------------------------------------

    for method in methods:

        if method.get("type") != "google_news":
            continue

        query = method.get("query")

        if not query:
            continue

        google_url = make_google_news_url(query)

        print(f"    Trying Google News RSS")
        print(f"    Query: {query}")

        entries = get_feed(google_url)

        if entries:
            print(f"    SUCCESS: {name} via Google News")

            return extract_articles(entries, source)

    print(f"    FAILED: No articles found for {name}")

    return []


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing")
        return False

    if not CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID is missing")
        return False

    telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            telegram_url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=REQUEST_TIMEOUT
        )

        print(f"Telegram status: {response.status_code}")
        print(response.text)

        return response.ok

    except Exception as e:
        print(f"Telegram ERROR: {e}")
        return False


# ============================================================
# Main
# ============================================================

def main():

    print("")
    print("🇸🇦 Saudi Economy Daily")
    print("Starting news collection...")
    print("")

    if not os.path.exists(SOURCES_FILE):
        print(f"ERROR: Sources file not found: {SOURCES_FILE}")
        return

    sources = load_sources()

    print(f"Enabled sources: {len(sources)}")

    all_articles = []
    seen_ids = set()

    # --------------------------------------------------------
    # Fetch all sources
    # --------------------------------------------------------

    for source in sources:

        try:
            articles = fetch_source(source)

            for article in articles:

                if article["id"] in seen_ids:
                    continue

                seen_ids.add(article["id"])
                all_articles.append(article)

        except Exception as e:
            print(
                f"ERROR while processing "
                f"{source.get('name', 'Unknown')}: {e}"
            )

    # --------------------------------------------------------
    # Sort by source priority
    # --------------------------------------------------------

    all_articles.sort(
        key=lambda x: x.get("priority", 1),
        reverse=True
    )

    print("")
    print("=" * 60)
    print(f"TOTAL ARTICLES FOUND: {len(all_articles)}")
    print("=" * 60)

    # --------------------------------------------------------
    # No articles
    # --------------------------------------------------------

    if not all_articles:
        print("No articles found.")
        return

    # --------------------------------------------------------
    # TEST MODE
    #
    # We intentionally send only a small number of articles
    # during the first test.
    # --------------------------------------------------------

    test_articles = all_articles[:10]

    print("")
    print(f"Sending {len(test_articles)} test articles to Telegram...")
    print("")

    success_count = 0

    for article in test_articles:

        message = (
            "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
            f"📰 <b>{article['title']}</b>\n\n"
            f"📌 المصدر: {article['source']}\n"
            f"🔗 {article['url']}"
        )

        print(f"Sending: {article['title']}")

        if send_telegram(message):
            success_count += 1

    print("")
    print("=" * 60)
    print(f"Telegram messages sent successfully: {success_count}/{len(test_articles)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
