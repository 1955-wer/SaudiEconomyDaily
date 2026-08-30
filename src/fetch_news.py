import os
import json
import hashlib
import requests
import feedparser
from urllib.parse import quote

from ai_editor import analyze_article


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCES_FILE = "config/sources.json"

MAX_ARTICLES_PER_SOURCE = 3
MAX_AI_ARTICLES = 3

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

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


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

        title = clean_text(
            entry.get("title", "")
        )

        url = clean_text(
            entry.get("link", "")
        )

        description = clean_text(
            entry.get("summary", "")
        )

        if not title or not url:
            continue

        articles.append({
            "id": article_id(title, url),
            "title": title,
            "url": url,
            "content": description,
            "source": source.get(
                "name",
                "مصدر غير معروف"
            ),
            "priority": source.get(
                "priority",
                1
            )
        })

    return articles


# ============================================================
# Source fetching
# ============================================================

def fetch_source(source):

    name = source.get(
        "name",
        "Unknown"
    )

    methods = list(
        source.get("methods", [])
    )

    # دعم sources.json القديم
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
    # Direct RSS
    # --------------------------------------------------------

    for method in methods:

        if method.get("type") != "rss":
            continue

        rss_url = method.get("url")

        if not rss_url:
            continue

        entries = get_feed(rss_url)

        if entries:

            print(
                f"    SUCCESS: {name} via RSS"
            )

            return extract_articles(
                entries,
                source
            )

    # --------------------------------------------------------
    # Google News RSS
    # --------------------------------------------------------

    for method in methods:

        if method.get("type") != "google_news":
            continue

        query = method.get("query")

        if not query:
            continue

        google_url = make_google_news_url(
            query
        )

        print(
            "    Trying Google News RSS"
        )

        entries = get_feed(
            google_url
        )

        if entries:

            print(
                f"    SUCCESS: {name} via Google News"
            )

            return extract_articles(
                entries,
                source
            )

    print(
        f"    FAILED: No articles found for {name}"
    )

    return []


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not TOKEN:
        print(
            "ERROR: TELEGRAM_BOT_TOKEN is missing"
        )
        return False

    if not CHAT_ID:
        print(
            "ERROR: TELEGRAM_CHAT_ID is missing"
        )
        return False

    telegram_url = (
        f"https://api.telegram.org/bot"
        f"{TOKEN}/sendMessage"
    )

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

        print(
            f"Telegram status: {response.status_code}"
        )

        if not response.ok:
            print(response.text)

        return response.ok

    except Exception as e:

        print(
            f"Telegram ERROR: {e}"
        )

        return False


# ============================================================
# Telegram message
# ============================================================

def build_message(article, ai):

    category = ai.get(
        "category",
        "economy"
    )

    category_names = {
        "oil": "النفط والطاقة",
        "markets": "الأسواق",
        "banks": "البنوك والقطاع المالي",
        "companies": "الشركات",
        "investment": "الاستثمار",
        "government": "الحكومة والأنظمة",
        "real_estate": "العقارات",
        "employment": "سوق العمل",
        "technology": "التقنية",
        "tourism": "السياحة",
        "industry": "الصناعة",
        "economy": "الاقتصاد",
        "other": "أخرى"
    }

    category_name = category_names.get(
        category,
        category
    )

    importance = ai.get(
        "importance",
        0
    )

    headline = clean_text(
        ai.get("headline", "")
    )

    summary = clean_text(
        ai.get("summary", "")
    )

    why = clean_text(
        ai.get("why_it_matters", "")
    )

    key_facts = ai.get(
        "key_facts",
        []
    )

    facts_text = ""

    if key_facts:

        facts_text = "\n\n".join(
            f"• {clean_text(fact)}"
            for fact in key_facts[:3]
        )

    message = (
        "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
        f"📰 <b>{headline}</b>\n\n"
        f"{summary}\n\n"
    )

    if facts_text:

        message += (
            "📌 <b>أبرز المعلومات:</b>\n"
            f"{facts_text}\n\n"
        )

    if why:

        message += (
            "💡 <b>لماذا يهم؟</b>\n"
            f"{why}\n\n"
        )

    message += (
        f"📊 القطاع: {category_name}\n"
        f"🔴 الأهمية: {importance}/100\n\n"
        f"📰 المصدر: {article['source']}\n"
        f"🔗 {article['url']}"
    )

    return message


# ============================================================
# Main
# ============================================================

def main():

    print("")
    print("🇸🇦 Saudi Economy Daily")
    print("Starting AI news collection...")
    print("")

    if not os.path.exists(
        SOURCES_FILE
    ):

        print(
            f"ERROR: Sources file not found: "
            f"{SOURCES_FILE}"
        )

        return

    sources = load_sources()

    print(
        f"Enabled sources: {len(sources)}"
    )

    all_articles = []
    seen_ids = set()

    # --------------------------------------------------------
    # Collect news
    # --------------------------------------------------------

    for source in sources:

        try:

            articles = fetch_source(
                source
            )

            for article in articles:

                if article["id"] in seen_ids:
                    continue

                seen_ids.add(
                    article["id"]
                )

                all_articles.append(
                    article
                )

        except Exception as e:

            print(
                f"ERROR while processing "
                f"{source.get('name', 'Unknown')}: {e}"
            )

    # --------------------------------------------------------
    # Sort by source priority
    # --------------------------------------------------------

    all_articles.sort(
        key=lambda x: x.get(
            "priority",
            1
        ),
        reverse=True
    )

    print("")
    print("=" * 60)
    print(
        f"TOTAL ARTICLES FOUND: "
        f"{len(all_articles)}"
    )
    print("=" * 60)

    if not all_articles:

        print(
            "No articles found."
        )

        return

    # --------------------------------------------------------
    # AI TEST
    # --------------------------------------------------------

    candidates = all_articles[
        :MAX_AI_ARTICLES
    ]

    print("")
    print(
        f"Sending {len(candidates)} "
        "articles to AI..."
    )
    print("")

    published = 0

    for index, article in enumerate(
        candidates,
        start=1
    ):

        print("")
        print(
            "=" * 60
        )

        print(
            f"AI ARTICLE {index}/{len(candidates)}"
        )

        print(
            f"Title: {article['title']}"
        )

        ai_result = analyze_article(
            article
        )

        if not ai_result:

            print(
                "AI failed. Skipping article."
            )

            continue

        print(
            "AI result:"
        )

        print(
            json.dumps(
                ai_result,
                ensure_ascii=False,
                indent=2
            )
        )

        publish = ai_result.get(
            "publish",
            False
        )

        importance = ai_result.get(
            "importance",
            0
        )

        # ----------------------------------------------------
        # Publish threshold
        # ----------------------------------------------------

        if (
            publish is True
            and importance >= 75
        ):

            message = build_message(
                article,
                ai_result
            )

            if send_telegram(
                message
            ):

                published += 1

                print(
                    "✅ Published to Telegram"
                )

        else:

            print(
                "❌ AI decided this article "
                "is not important enough."
            )

    print("")
    print("=" * 60)

    print(
        f"AI articles published: "
        f"{published}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()

