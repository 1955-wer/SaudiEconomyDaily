import os
import json
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup

from ai_editor import analyze_articles


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCES_FILE = "config/sources.json"

STATE_DIR = "data"
STATE_FILE = os.path.join(STATE_DIR, "processed_articles.json")

# جمع أخبار أكثر من كل مصدر
MAX_ARTICLES_PER_SOURCE = 12

# عدد الأخبار التي يفحصها AI في كل تشغيل
MAX_AI_ARTICLES = 14

# حجم الدفعة الواحدة إلى AI
AI_BATCH_SIZE = 5

# شروط النشر
PUBLISH_THRESHOLD = 70
MIN_CONFIDENCE = 50

MAX_ARTICLE_AGE_HOURS = 36
MAX_CONTENT_LENGTH = 18000

REQUEST_TIMEOUT = 25

STATE_RETENTION_DAYS = 30


# ============================================================
# Economic keywords
# ============================================================

ECONOMIC_KEYWORDS = [
    "اقتصاد", "اقتصادي", "الاقتصاد",
    "نفط", "أرامكو", "أوبك", "أوبك+",
    "طاقة", "غاز",
    "استثمار", "استثمارات", "استثمار أجنبي",
    "تمويل", "بنك", "بنوك",
    "فائدة", "تضخم", "سيولة",
    "تاسي", "أسهم", "سوق الأسهم", "تداول",
    "شركة", "شركات",
    "أرباح", "إيرادات", "خسائر",
    "استحواذ", "اندماج",
    "مشروع", "مشاريع",
    "ميزانية", "دين", "صكوك", "سندات",
    "تجارة", "صادرات", "واردات",
    "عقار", "عقارات",
    "سياحة",
    "صناعة", "تصنيع",
    "تعدين",
    "وظائف", "توظيف", "توطين",
    "رؤية 2030",
    "صندوق الاستثمارات",
    "القطاع الخاص",
    "ناتج محلي",
    "نمو",
    "مؤشر",
    "ترخيص",
    "تنظيم",
    "صفقة",
    "اكتتاب",
]


# ============================================================
# Reject obvious non-news pages
# ============================================================

REJECT_TITLE_PATTERNS = [
    "معلومات الشركة",
    "أخبار ومعلومات سوق الأسهم",
    "معلومات الشركة -",
    "أسعار الأسهم",
    "سعر السهم",
    "السوق السعودي مباشر",
    "شاشة التداول",
    "ملف الشركة",
    "Company Information",
    "Stock Information",
    "أسعار الذهب",
    "أسعار النفط اليوم",
]


# ============================================================
# Basic helpers
# ============================================================

def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        source
        for source in data.get("sources", [])
        if source.get("enabled", True)
    ]


def load_state():
    os.makedirs(STATE_DIR, exist_ok=True)

    if not os.path.exists(STATE_FILE):
        return {"processed": {}}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"processed": {}}

        if not isinstance(data.get("processed"), dict):
            data["processed"] = {}

        return data

    except Exception as error:
        print(f"WARNING: Could not load state: {error}")
        return {"processed": {}}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def cleanup_state(state):
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=STATE_RETENTION_DAYS)
    )

    cleaned = {}

    for article_id, timestamp in state.get("processed", {}).items():
        try:
            dt = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )

            if dt >= cutoff:
                cleaned[article_id] = timestamp

        except Exception:
            continue

    state["processed"] = cleaned
    return state


def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def remove_html(text):
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")

    return clean_text(
        soup.get_text(" ")
    )


def article_id(title, url):
    value = (
        clean_text(title).lower()
        + "|"
        + clean_text(url).lower()
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def title_key(title):
    title = clean_text(title).lower()

    title = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        title,
    )

    words = title.split()

    stop_words = {
        "السعودية",
        "السعودي",
        "اليوم",
        "في",
        "من",
        "عن",
        "على",
        "إلى",
        "مع",
        "بعد",
        "قبل",
        "نشر",
        "تعلن",
        "يعلن",
    }

    words = [
        word
        for word in words
        if word not in stop_words
    ]

    return " ".join(words)


def contains_economic_keyword(title):
    title = title.lower()

    score = 0

    for keyword in ECONOMIC_KEYWORDS:
        if keyword.lower() in title:
            score += 1

    return min(score, 12)


def is_rejected_title(title):
    lowered = title.lower()

    return any(
        pattern.lower() in lowered
        for pattern in REJECT_TITLE_PATTERNS
    )


# ============================================================
# Dates
# ============================================================

def parse_entry_date(entry):
    for field in ("published", "updated"):
        value = entry.get(field)

        if not value:
            continue

        try:
            dt = parsedate_to_datetime(value)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)

        except Exception:
            continue

    return None


def is_recent(article):
    published_at = article.get("published_at")

    if not published_at:
        return True

    try:
        dt = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        age_hours = (
            datetime.now(timezone.utc) - dt
        ).total_seconds() / 3600

        return age_hours <= MAX_ARTICLE_AGE_HOURS

    except Exception:
        return True


# ============================================================
# RSS
# ============================================================

def get_feed(url):
    try:
        print(f"    RSS: {url}")

        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent":
                    "Mozilla/5.0 SaudiEconomyDaily/4.0"
            },
        )

        if not feed.entries:
            print("    RSS: no entries")
            return []

        print(
            f"    RSS entries: "
            f"{len(feed.entries)}"
        )

        return feed.entries

    except Exception as error:
        print(f"    RSS ERROR: {error}")
        return []


# ============================================================
# Website extraction
# ============================================================

def fetch_website_links(page_url, source):
    try:
        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/131 Safari/537.36"
        }

        response = requests.get(
            page_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            print(
                f"    Website status: "
                f"{response.status_code}"
            )
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        source_domain = urlparse(
            source.get("url", page_url)
        ).netloc

        results = []
        seen = set()

        for anchor in soup.find_all(
            "a",
            href=True,
        ):
            text = clean_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

            href = anchor.get(
                "href",
                "",
            )

            if len(text) < 30:
                continue

            if len(text) > 220:
                continue

            if href.startswith("#"):
                continue

            if href.startswith("javascript:"):
                continue

            absolute_url = urljoin(
                page_url,
                href,
            )

            domain = urlparse(
                absolute_url
            ).netloc

            if source_domain and domain:
                if source_domain not in domain:
                    continue

            if absolute_url in seen:
                continue

            if is_rejected_title(text):
                continue

            # Prefer links with economic wording.
            economic_score = contains_economic_keyword(
                text
            )

            if economic_score == 0 and len(results) >= 4:
                continue

            seen.add(absolute_url)

            results.append(
                {
                    "title": text,
                    "url": absolute_url,
                }
            )

            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break

        return results

    except Exception as error:
        print(f"    Website ERROR: {error}")
        return []


# ============================================================
# Article text extraction
# ============================================================

def extract_article_text(url):
    if not url:
        return ""

    try:
        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/131 Safari/537.36"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "nav",
                "footer",
                "header",
                "form",
                "aside",
            ]
        ):
            tag.decompose()

        candidates = []

        candidates.extend(
            soup.find_all("article")
        )

        candidates.extend(
            soup.find_all("main")
        )

        candidates.extend(
            soup.find_all(
                "div",
                class_=re.compile(
                    r"article|story|content|post|entry|body|article-body",
                    re.I,
                ),
            )
        )

        best_text = ""

        for candidate in candidates:
            text = clean_text(
                candidate.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) > len(best_text):
                best_text = text

        if len(best_text) < 300:
            body = soup.find("body")

            if body:
                best_text = clean_text(
                    body.get_text(
                        " ",
                        strip=True,
                    )
                )

        if len(best_text) < 200:
            return ""

        return best_text[:MAX_CONTENT_LENGTH]

    except Exception as error:
        print(
            f"    Article extraction ERROR: {error}"
        )
        return ""


# ============================================================
# Article builder
# ============================================================

def build_article(
    title,
    url,
    description,
    source,
    published_at=None,
):
    if not title or not url:
        return None

    title = clean_text(title)

    if is_rejected_title(title):
        return None

    full_content = extract_article_text(url)

    if len(full_content) >= 200:
        content = full_content
    else:
        content = remove_html(description)

    if not content:
        content = title

    return {
        "id": article_id(title, url),
        "title": title,
        "url": url,
        "content": content,
        "source": source.get(
            "name",
            "Unknown",
        ),
        "priority": int(
            source.get(
                "priority",
                1,
            )
        ),
        "published_at": (
            published_at.isoformat()
            if published_at
            else None
        ),
    }


def rss_articles(entries, source):
    articles = []

    for entry in entries:
        title = clean_text(
            entry.get(
                "title",
                "",
            )
        )

        url = clean_text(
            entry.get(
                "link",
                "",
            )
        )

        description = entry.get(
            "summary",
            "",
        )

        published_at = parse_entry_date(
            entry
        )

        article = build_article(
            title,
            url,
            description,
            source,
            published_at,
        )

        if article and is_recent(article):
            articles.append(article)

        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

    return articles


# ============================================================
# Source fetching
# ============================================================

def fetch_source(source):
    name = source.get(
        "name",
        "Unknown",
    )

    methods = list(
        source.get(
            "methods",
            [],
        )
    )

    print("")
    print("=" * 60)
    print(f"SOURCE: {name}")
    print("=" * 60)

    all_results = []

    # RSS
    for method in methods:
        if method.get("type") != "rss":
            continue

        url = method.get("url")

        if not url:
            continue

        entries = get_feed(url)

        if entries:
            all_results.extend(
                rss_articles(
                    entries,
                    source,
                )
            )

    # Google News
    for method in methods:
        if method.get("type") != "google_news":
            continue

        query = method.get("query")

        if not query:
            continue

        google_url = (
            "https://news.google.com/rss/search?"
            f"q={quote(query)}"
            "&hl=ar"
            "&gl=SA"
            "&ceid=SA:ar"
        )

        entries = get_feed(
            google_url
        )

        if entries:
            all_results.extend(
                rss_articles(
                    entries,
                    source,
                )
            )

    # Website
    for method in methods:
        if method.get("type") != "website":
            continue

        page_url = method.get("url")

        if not page_url:
            continue

        links = fetch_website_links(
            page_url,
            source,
        )

        for link in links:
            article = build_article(
                link["title"],
                link["url"],
                "",
                source,
                datetime.now(timezone.utc),
            )

            if article:
                all_results.append(article)

    unique = {}

    for article in all_results:
        unique[article["id"]] = article

    results = list(
        unique.values()
    )

    print(
        f"    Source articles: {len(results)}"
    )

    return results


# ============================================================
# Candidate scoring
# ============================================================

def candidate_score(article):
    score = 0

    score += (
        article.get(
            "priority",
            1,
        )
        * 10
    )

    score += (
        contains_economic_keyword(
            article.get(
                "title",
                "",
            )
        )
        * 4
    )

    published_at = article.get(
        "published_at"
    )

    if published_at:
        try:
            dt = datetime.fromisoformat(
                published_at.replace(
                    "Z",
                    "+00:00",
                )
            )

            age_hours = (
                datetime.now(timezone.utc)
                - dt
            ).total_seconds() / 3600

            if age_hours <= 3:
                score += 40
            elif age_hours <= 6:
                score += 35
            elif age_hours <= 12:
                score += 30
            elif age_hours <= 24:
                score += 20
            elif age_hours <= 36:
                score += 10

        except Exception:
            pass

    if len(
        article.get(
            "content",
            "",
        )
    ) >= 1000:
        score += 10

    return score


def select_ai_candidates(articles):
    ordered = sorted(
        articles,
        key=candidate_score,
        reverse=True,
    )

    selected = []
    source_counts = {}

    # Prefer source diversity first.
    for article in ordered:
        source = article.get(
            "source",
            "Unknown",
        )

        count = source_counts.get(
            source,
            0,
        )

        if count >= 2:
            continue

        selected.append(article)
        source_counts[source] = count + 1

        if len(selected) >= MAX_AI_ARTICLES:
            return selected

    # Fill remaining slots.
    for article in ordered:
        if article in selected:
            continue

        selected.append(article)

        if len(selected) >= MAX_AI_ARTICLES:
            break

    return selected


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

    url = (
        f"https://api.telegram.org/bot"
        f"{TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=REQUEST_TIMEOUT,
        )

        print(
            f"Telegram status: {response.status_code}"
        )

        if not response.ok:
            print(
                response.text[:2000]
            )

        return response.ok

    except Exception as error:
        print(
            f"Telegram ERROR: {error}"
        )
        return False


# ============================================================
# Telegram message
# ============================================================

def build_message(article, ai):
    categories = {
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
        "mining": "التعدين",
        "transport": "النقل والبنية التحتية",
        "economy": "الاقتصاد",
        "other": "أخرى",
    }

    impact_names = {
        "positive": "إيجابي",
        "negative": "سلبي",
        "neutral": "محايد",
        "mixed": "مختلط",
        "unknown": "غير محدد",
    }

    category = categories.get(
        ai.get(
            "category",
            "other",
        ),
        "أخرى",
    )

    impact = impact_names.get(
        ai.get(
            "market_impact",
            "unknown",
        ),
        "غير محدد",
    )

    headline = clean_text(
        ai.get(
            "headline",
            "",
        )
    )

    summary = clean_text(
        ai.get(
            "summary",
            "",
        )
    )

    why = clean_text(
        ai.get(
            "why_it_matters",
            "",
        )
    )

    importance = ai.get(
        "importance",
        0,
    )

    confidence = ai.get(
        "confidence",
        0,
    )

    facts = ai.get(
        "key_facts",
        [],
    )

    entities = ai.get(
        "affected_entities",
        [],
    )

    message = (
        "🇸🇦 <b>Saudi Economy Daily</b>\n\n"
        f"📰 <b>{headline}</b>\n\n"
        f"{summary}\n\n"
    )

    if facts:
        message += (
            "📌 <b>أبرز المعلومات:</b>\n"
        )

        for fact in facts[:3]:
            message += (
                f"• {clean_text(fact)}\n"
            )

        message += "\n"

    if entities:
        message += (
            "🏢 <b>الجهات المتأثرة:</b>\n"
            + "، ".join(
                clean_text(x)
                for x in entities[:5]
            )
            + "\n\n"
        )

    if why:
        message += (
            "💡 <b>لماذا يهم؟</b>\n"
            f"{why}\n\n"
        )

    message += (
        f"📊 القطاع: {category}\n"
        f"📈 التأثير المحتمل: {impact}\n"
        f"🔴 الأهمية: {importance}/100\n"
        f"🎯 الثقة: {confidence}/100\n\n"
        f"📰 المصدر: {article['source']}\n"
        f"🔗 {article['url']}"
    )

    return message


# ============================================================
# Main
# ============================================================

def main():
    print("")
    print("🇸🇦 Saudi Economy Daily 4.0")
    print("Starting...")
    print("")

    if not os.path.exists(SOURCES_FILE):
        print(
            "ERROR: sources.json not found"
        )
        return

    sources = load_sources()

    print(
        f"Enabled sources: {len(sources)}"
    )

    state = cleanup_state(
        load_state()
    )

    processed = state.get(
        "processed",
        {}
    )

    all_articles = []

    seen_ids = set()
    seen_titles = set()

    # --------------------------------------------------------
    # Collect
    # --------------------------------------------------------

    for source in sources:
        try:
            source_articles = fetch_source(
                source
            )

            for article in source_articles:
                aid = article["id"]

                if aid in processed:
                    continue

                if aid in seen_ids:
                    continue

                normalized_title = title_key(
                    article["title"]
                )

                if (
                    normalized_title
                    and normalized_title in seen_titles
                ):
                    continue

                seen_ids.add(aid)

                if normalized_title:
                    seen_titles.add(
                        normalized_title
                    )

                all_articles.append(
                    article
                )

        except Exception as error:
            print(
                f"Source ERROR: {error}"
            )

    print("")
    print("=" * 60)
    print(
        f"NEW ARTICLES: {len(all_articles)}"
    )
    print("=" * 60)

    if not all_articles:
        save_state(state)
        print("No new articles.")
        return

    candidates = select_ai_candidates(
        all_articles
    )

    print("")
    print(
        f"AI candidates: {len(candidates)}"
    )
    print(
        f"AI batch size: {AI_BATCH_SIZE}"
    )
    print("")

    published = 0
    processed_now = 0

    # --------------------------------------------------------
    # Analyze in batches
    # --------------------------------------------------------

    for batch_start in range(
        0,
        len(candidates),
        AI_BATCH_SIZE,
    ):
        batch = candidates[
            batch_start:
            batch_start + AI_BATCH_SIZE
        ]

        batch_number = (
            batch_start // AI_BATCH_SIZE
        ) + 1

        total_batches = (
            len(candidates)
            + AI_BATCH_SIZE
            - 1
        ) // AI_BATCH_SIZE

        print("")
        print("=" * 60)
        print(
            f"AI BATCH "
            f"{batch_number}/{total_batches}"
        )

        for article in batch:
            print(
                f"- {article['title']}"
            )

        results = analyze_articles(
            batch
        )

        if not results:
            print(
                "AI batch failed."
            )
            continue

        for article in batch:
            aid = str(
                article["id"]
            )

            result = results.get(
                aid
            )

            if not result:
                print(
                    f"Missing AI result: "
                    f"{article['title']}"
                )
                continue

            print("")
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            # Save successful AI processing.
            processed[aid] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            processed_now += 1

            publish = result.get(
                "publish",
                False,
            )

            importance = result.get(
                "importance",
                0,
            )

            confidence = result.get(
                "confidence",
                0,
            )

            if (
                publish
                and importance >= PUBLISH_THRESHOLD
                and confidence >= MIN_CONFIDENCE
            ):
                message = build_message(
                    article,
                    result,
                )

                if send_telegram(
                    message
                ):
                    published += 1
                    print(
                        "✅ Published"
                    )
                    time.sleep(1)

            else:
                print(
                    "❌ Not published"
                )

    state["processed"] = processed

    save_state(state)

    print("")
    print("=" * 60)
    print(
        f"Successfully processed: "
        f"{processed_now}"
    )
    print(
        f"Published: {published}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
