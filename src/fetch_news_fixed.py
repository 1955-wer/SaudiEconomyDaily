import os
import json
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo
from io import BytesIO

import requests
import feedparser
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from ai_editor import analyze_articles


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCES_FILE_CANDIDATES = [
    "config/sources.json",
    "sources.json",
]

STATE_DIR = "data"
STATE_FILE = os.path.join(
    STATE_DIR,
    "processed_articles.json"
)

MAX_ARTICLES_PER_SOURCE = 10
MAX_CANDIDATES_PER_RUN = 6
MAX_ITEMS_PER_NEWSLETTER = 3

# 3 newsletters × 3 items = 9 items on a normal day.
DAILY_TARGET = 9
DAILY_MIN = 8
DAILY_MAX = 10

PUBLISH_THRESHOLD = 68
MIN_CONFIDENCE = 50

# Each run looks mainly at the last 30 hours.
MAX_ARTICLE_AGE_HOURS = 30

# Only selected AI candidates get full article extraction.
MAX_CONTENT_LENGTH = 18000

REQUEST_TIMEOUT = 20
STATE_RETENTION_DAYS = 30
ANALYSIS_RETRY_HOURS = 18

RIYADH = ZoneInfo("Asia/Riyadh")


ECONOMIC_KEYWORDS = [
    "اقتصاد", "اقتصادي", "الاقتصاد",
    "نفط", "أرامكو", "أوبك", "أوبك+",
    "طاقة", "غاز", "استثمار", "استثمارات",
    "تمويل", "بنك", "بنوك", "فائدة", "تضخم",
    "تاسي", "أسهم", "سوق الأسهم", "تداول",
    "شركة", "شركات", "أرباح", "إيرادات", "خسائر",
    "استحواذ", "اندماج", "صفقة",
    "مشروع", "مشاريع", "ميزانية", "دين",
    "صكوك", "سندات", "تجارة", "صادرات", "واردات",
    "عقار", "عقارات", "سياحة", "صناعة", "تصنيع",
    "تعدين", "وظائف", "توظيف", "توطين",
    "رؤية 2030", "صندوق الاستثمارات", "القطاع الخاص",
    "ناتج محلي", "نمو", "مؤشر", "تنظيم", "اكتتاب",
    "إنتاج", "شحن", "لوجستيات", "سلاسل الإمداد",
]

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
    "سعر النفط اليوم",
]


def find_sources_file():
    for path in SOURCES_FILE_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def load_sources():
    sources_file = find_sources_file()

    if not sources_file:
        print("ERROR: sources.json not found in config/ or project root")
        return []

    print(f"Using sources file: {sources_file}")

    try:
        with open(sources_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as error:
        print(f"ERROR: Invalid sources.json: {error}")
        return []
    except OSError as error:
        print(f"ERROR: Could not read sources.json: {error}")
        return []

    return [
        source
        for source in data.get("sources", [])
        if source.get("enabled", True)
    ]


def load_state():
    os.makedirs(STATE_DIR, exist_ok=True)

    if not os.path.exists(STATE_FILE):
        return {
            "processed": {},
            "published": {},
            "daily": {
                "date": "",
                "count": 0,
                "newsletter_count": 0,
                "ids": [],
                "content_types": [],
            },
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            data = {}

        data.setdefault("processed", {})
        data.setdefault("published", {})
        data.setdefault(
            "daily",
            {
                "date": "",
                "count": 0,
                "newsletter_count": 0,
                "ids": [],
                "content_types": [],
            },
        )

        return data

    except Exception as error:
        print(f"WARNING: Could not load state: {error}")
        return {
            "processed": {},
            "published": {},
            "daily": {
                "date": "",
                "count": 0,
                "newsletter_count": 0,
                "ids": [],
                "content_types": [],
            },
        }


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def prepare_daily_state(state):
    today = datetime.now(RIYADH).date().isoformat()
    daily = state.get("daily", {})

    if daily.get("date") != today:
        state["daily"] = {
            "date": today,
            "count": 0,
            "newsletter_count": 0,
            "ids": [],
            "content_types": [],
        }

    return state


def cleanup_state(state):
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=STATE_RETENTION_DAYS
    )

    for key in ("processed", "published"):
        old = state.get(key, {})
        cleaned = {}

        for article_id, timestamp in old.items():
            try:
                dt = datetime.fromisoformat(
                    str(timestamp).replace("Z", "+00:00")
                )
                if dt >= cutoff:
                    cleaned[article_id] = timestamp
            except Exception:
                continue

        state[key] = cleaned

    return state


def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", str(text)).strip()


def remove_html(text):
    if not text:
        return ""

    soup = BeautifulSoup(
        text,
        "html.parser"
    )

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
        title
    )

    stop_words = {
        "السعودية", "السعودي", "اليوم", "في",
        "من", "عن", "على", "إلى", "مع", "بعد",
        "قبل", "تعلن", "يعلن", "نشر", "وكالة",
    }

    return " ".join(
        word
        for word in title.split()
        if word not in stop_words
    )


def contains_economic_keyword(title):
    title = title.lower()

    return min(
        sum(
            1
            for keyword in ECONOMIC_KEYWORDS
            if keyword.lower() in title
        ),
        15,
    )


def is_rejected_title(title):
    lowered = title.lower()

    return any(
        pattern.lower() in lowered
        for pattern in REJECT_TITLE_PATTERNS
    )


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


def get_feed(url):
    try:
        print(f"    RSS: {url}")

        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent":
                    "Mozilla/5.0 SaudiEconomyDaily/5.0"
            },
        )

        if not feed.entries:
            return []

        print(
            f"    RSS entries: {len(feed.entries)}"
        )

        return feed.entries

    except Exception as error:
        print(f"    RSS ERROR: {error}")
        return []


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
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
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
                ""
            )

            if len(text) < 30 or len(text) > 240:
                continue

            if href.startswith(("#", "javascript:")):
                continue

            absolute_url = urljoin(
                page_url,
                href
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

            if contains_economic_keyword(text) == 0 and len(results) >= 5:
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
        print(
            f"    Website ERROR: {error}"
        )
        return []


def extract_pdf_text(url):
    if PdfReader is None:
        print("    pypdf is not installed; cannot read PDF.")
        return ""

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 SaudiEconomyDaily/5.0"
            },
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return ""

        reader = PdfReader(
            BytesIO(response.content)
        )

        pages = []

        for page in reader.pages[:25]:
            text = page.extract_text() or ""
            if text:
                pages.append(text)

        return clean_text(
            "\n".join(pages)
        )[:MAX_CONTENT_LENGTH]

    except Exception as error:
        print(
            f"    PDF extraction ERROR: {error}"
        )
        return ""


def extract_article_text(url):
    if not url:
        return ""

    lower_url = url.lower().split("?")[0]

    if lower_url.endswith(".pdf"):
        return extract_pdf_text(url)

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/131 Safari/537.36"
            },
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return ""

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if "application/pdf" in content_type:
            return extract_pdf_text(url)

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for tag in soup(
            [
                "script", "style", "noscript", "svg",
                "nav", "footer", "header", "form",
                "aside"
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
                    r"article|story|content|post|entry|body|article-body|report",
                    re.I,
                ),
            )
        )

        best_text = ""

        for candidate in candidates:
            text = clean_text(
                candidate.get_text(
                    " ",
                    strip=True
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
                        strip=True
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

    default_type = source.get(
        "default_content_type",
        "news"
    )

    content = remove_html(
        description
    )

    return {
        "id": article_id(title, url),
        "title": title,
        "url": url,
        "content": content or title,
        "source": source.get("name", "Unknown"),
        "source_type": source.get("type", "news"),
        "default_content_type": default_type,
        "priority": int(
            source.get("priority", 1)
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
        article = build_article(
            clean_text(entry.get("title", "")),
            clean_text(entry.get("link", "")),
            entry.get("summary", ""),
            source,
            parse_entry_date(entry),
        )

        if article and is_recent(article):
            articles.append(article)

        if len(articles) >= MAX_ARTICLES_PER_SOURCE:
            break

    return articles


def fetch_source(source):
    name = source.get("name", "Unknown")

    methods = list(
        source.get("methods", [])
    )

    print("")
    print("=" * 60)
    print(f"SOURCE: {name}")
    print("=" * 60)

    all_results = []

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
                    source
                )
            )

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
                    source
                )
            )

    for method in methods:
        if method.get("type") != "website":
            continue

        page_url = method.get("url")

        if not page_url:
            continue

        links = fetch_website_links(
            page_url,
            source
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
                all_results.append(
                    article
                )

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


def candidate_score(article):
    score = (
        article.get("priority", 1) * 10
    )

    score += (
        contains_economic_keyword(
            article.get("title", "")
        ) * 4
    )

    content_type = article.get(
        "default_content_type",
        "news"
    )

    if content_type == "analysis":
        score += 16
    elif content_type == "report":
        score += 14
    elif content_type == "data":
        score += 12

    published_at = article.get(
        "published_at"
    )

    if published_at:
        try:
            dt = datetime.fromisoformat(
                published_at.replace(
                    "Z",
                    "+00:00"
                )
            )

            age_hours = (
                datetime.now(timezone.utc) - dt
            ).total_seconds() / 3600

            if age_hours <= 3:
                score += 40
            elif age_hours <= 6:
                score += 34
            elif age_hours <= 12:
                score += 28
            elif age_hours <= 24:
                score += 20
            elif age_hours <= 30:
                score += 10

        except Exception:
            pass

    # Strong RSS summary / content is a useful signal.
    if len(
        article.get("content", "")
    ) >= 600:
        score += 8

    return score


def select_candidates(
    articles,
    target,
):
    ordered = sorted(
        articles,
        key=candidate_score,
        reverse=True,
    )

    selected = []
    sources = set()
    types = set()

    # First pass: source and content-type diversity.
    for article in ordered:
        source = article.get("source", "")
        content_type = article.get(
            "default_content_type",
            "news"
        )

        if source in sources:
            continue

        if content_type not in types or len(selected) >= target - 2:
            selected.append(article)
            sources.add(source)
            types.add(content_type)

        if len(selected) >= target:
            return selected

    # Second pass: fill remaining slots.
    for article in ordered:
        if article in selected:
            continue

        selected.append(article)

        if len(selected) >= target:
            break

    return selected


def enrich_articles(articles):
    for article in articles:
        text = extract_article_text(
            article["url"]
        )

        if len(text) >= 250:
            article["content"] = text

        print(
            f"    Enriched: {article['title'][:100]}"
        )

    return articles


def newsletter_label():
    now = datetime.now(RIYADH)

    if now.hour < 11:
        return "نشرة الصباح"
    if now.hour < 17:
        return "نشرة منتصف اليوم"

    return "النشرة المسائية"


def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print(
            "ERROR: Telegram credentials missing"
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
            print(response.text[:2000])

        return response.ok

    except Exception as error:
        print(
            f"Telegram ERROR: {error}"
        )
        return False


def format_item(article, result, number):
    type_names = {
        "news": "خبر",
        "analysis": "تحليل",
        "report": "تقرير",
        "data": "بيانات",
    }

    impact_names = {
        "positive": "إيجابي",
        "negative": "سلبي",
        "neutral": "محايد",
        "mixed": "مختلط",
        "unknown": "غير محدد",
    }

    content_type = type_names.get(
        result.get("content_type", "news"),
        "خبر"
    )

    impact = impact_names.get(
        result.get("market_impact", "unknown"),
        "غير محدد"
    )

    text = (
        f"{number}) <b>{result.get('headline', article['title'])}</b>\n"
        f"🏷️ {content_type} · {result.get('category', 'economy')}\n"
        f"{result.get('summary', '')}\n"
    )

    why = result.get(
        "why_it_matters",
        ""
    ).strip()

    if why:
        text += (
            f"💡 {why}\n"
        )

    facts = result.get(
        "key_facts",
        []
    )

    if facts:
        text += (
            "📌 "
            + " | ".join(
                facts[:2]
            )
            + "\n"
        )

    text += (
        f"📈 الأثر: {impact}\n"
        f"📰 {article['source']}\n"
        f"🔗 {article['url']}\n"
    )

    return text


def build_newsletter(
    label,
    items,
):
    date_text = datetime.now(
        RIYADH
    ).strftime("%Y-%m-%d")

    parts = [
        "🇸🇦 <b>Saudi Economy Daily</b>",
        f"<b>{label}</b> · {date_text}",
        "",
        "أهم الأخبار والتحليلات الاقتصادية:",
        "",
    ]

    for index, item in enumerate(
        items,
        start=1,
    ):
        parts.append(
            format_item(
                item["article"],
                item["result"],
                index,
            )
        )
        parts.append("")

    parts.append(
        "🔎 أخبار ومحتوى مختصر، مع أولوية للمصادر الاقتصادية الرسمية والعالمية."
    )

    return "\n".join(parts)


def choose_publishable(
    candidates,
    results,
    slots,
):
    scored = []

    for article in candidates:
        result = results.get(
            str(article["id"])
        )

        if not result:
            continue

        if not result.get("publish", False):
            continue

        importance = int(
            result.get("importance", 0)
        )

        confidence = int(
            result.get("confidence", 0)
        )

        if importance < PUBLISH_THRESHOLD:
            continue

        if confidence < MIN_CONFIDENCE:
            continue

        scored.append(
            {
                "article": article,
                "result": result,
            }
        )

    scored.sort(
        key=lambda x: (
            x["result"].get(
                "importance",
                0
            ),
            x["result"].get(
                "confidence",
                0
            ),
        ),
        reverse=True,
    )

    selected = []
    used_types = set()
    used_sources = set()

    # Prefer at least one analytical/report/data item when available.
    for item in scored:
        content_type = item["result"].get(
            "content_type",
            "news"
        )

        if (
            content_type in {
                "analysis",
                "report",
                "data",
            }
            and content_type not in used_types
        ):
            selected.append(item)
            used_types.add(content_type)
            used_sources.add(
                item["article"]["source"]
            )
            break

    # Fill the remaining slots with quality + source diversity.
    for item in scored:
        if item in selected:
            continue

        source = item["article"]["source"]

        if source in used_sources and len(selected) < slots - 1:
            continue

        selected.append(item)
        used_sources.add(source)
        used_types.add(
            item["result"].get(
                "content_type",
                "news"
            )
        )

        if len(selected) >= slots:
            break

    # If source diversity prevented filling the slots, fill by score.
    for item in scored:
        if item in selected:
            continue

        selected.append(item)

        if len(selected) >= slots:
            break

    return selected[:slots]


def main():
    print("")
    print("🇸🇦 Saudi Economy Daily 5.0")
    print("Starting...")
    print("")

    sources = load_sources()

    if not sources:
        print("ERROR: No enabled sources were loaded.")
        return

    print(
        f"Enabled sources: {len(sources)}"
    )

    state = cleanup_state(
        load_state()
    )

    state = prepare_daily_state(
        state
    )

    daily = state["daily"]
    processed = state["processed"]
    published = state["published"]

    if daily["count"] >= DAILY_MAX:
        print(
            "Daily maximum reached. Skipping."
        )
        save_state(state)
        return

    all_articles = []
    seen_ids = set()
    seen_titles = set()

    # --------------------------------------------------------
    # Collect sources
    # --------------------------------------------------------

    for source in sources:
        try:
            for article in fetch_source(source):
                aid = article["id"]

                if aid in published:
                    continue

                if aid in daily["ids"]:
                    continue

                if aid in seen_ids:
                    continue

                normalized = title_key(
                    article["title"]
                )

                if (
                    normalized
                    and normalized in seen_titles
                ):
                    continue

                seen_ids.add(aid)

                if normalized:
                    seen_titles.add(normalized)

                all_articles.append(article)

        except Exception as error:
            print(
                f"Source ERROR: {error}"
            )

    print("")
    print("=" * 60)
    print(
        f"NEW CANDIDATES: {len(all_articles)}"
    )
    print("=" * 60)

    if not all_articles:
        save_state(state)
        print(
            "No new articles."
        )
        return

    # Do not recycle AI-rejected items too quickly.
    recent_cutoff = datetime.now(
        timezone.utc
    ) - timedelta(
        hours=ANALYSIS_RETRY_HOURS
    )

    fresh_candidates = []

    for article in all_articles:
        aid = article["id"]

        if aid not in processed:
            fresh_candidates.append(article)
            continue

        try:
            last_time = datetime.fromisoformat(
                str(processed[aid]).replace(
                    "Z",
                    "+00:00"
                )
            )

            if last_time < recent_cutoff:
                fresh_candidates.append(article)

        except Exception:
            fresh_candidates.append(article)

    if not fresh_candidates:
        fresh_candidates = all_articles

    candidates = select_candidates(
        fresh_candidates,
        MAX_CANDIDATES_PER_RUN,
    )

    # Only the small candidate set gets full page/PDF extraction.
    candidates = enrich_articles(
        candidates
    )

    # Normal newsletter size: 3 items.
    # On the third newsletter, allow a 4th item when needed
    # to reach the daily floor of 8 without exceeding 10.
    if daily["newsletter_count"] >= 2 and daily["count"] < DAILY_MIN:
        newsletter_capacity = 4
    else:
        newsletter_capacity = MAX_ITEMS_PER_NEWSLETTER

    slots = min(
        newsletter_capacity,
        DAILY_MAX - daily["count"],
    )

    print("")
    print(
        f"Newsletter slots: {slots}"
    )

    results = analyze_articles(
        candidates
    )

    if not results:
        print(
            "AI analysis failed."
        )
        save_state(state)
        return

    chosen = choose_publishable(
        candidates,
        results,
        slots,
    )

    print(
        f"Chosen for newsletter: {len(chosen)}"
    )

    if not chosen:
        print(
            "No items passed the publish threshold."
        )

        # Mark analyzed candidates so the same weak items
        # are not repeatedly sent to AI in the same window.
        now = datetime.now(
            timezone.utc
        ).isoformat()

        for article in candidates:
            processed[article["id"]] = now

        save_state(state)
        return

    message = build_newsletter(
        newsletter_label(),
        chosen,
    )

    if send_telegram(message):
        now = datetime.now(
            timezone.utc
        ).isoformat()

        for item in chosen:
            aid = item["article"]["id"]

            published[aid] = now
            daily["ids"].append(aid)
            daily["count"] += 1
            daily["content_types"].append(
                item["result"].get(
                    "content_type",
                    "news"
                )
            )

        daily["newsletter_count"] += 1

        for article in candidates:
            processed[article["id"]] = now

        print("")
        print(
            f"✅ {newsletter_label()} sent."
        )
        print(
            f"Daily published count: {daily['count']}"
        )
    else:
        print(
            "Newsletter sending failed."
        )

    save_state(state)

    print("")
    print("=" * 60)
    print(
        f"Daily total: {daily['count']} / {DAILY_TARGET} target"
    )
    print(
        f"Newsletters today: "
        f"{daily['newsletter_count']} / 3"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
