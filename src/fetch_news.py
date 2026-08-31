import os
import json
import hashlib
import re
import time

import requests
import feedparser

from bs4 import BeautifulSoup
from urllib.parse import quote


from ai_editor import analyze_article


# ============================================================
# Configuration
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SOURCES_FILE = "config/sources.json"

# عدد الأخبار التي نأخذها من كل مصدر
MAX_ARTICLES_PER_SOURCE = 3

# عدد الأخبار التي نرسلها للذكاء الاصطناعي
MAX_AI_ARTICLES = 10

# الحد الأدنى للأهمية للنشر
PUBLISH_THRESHOLD = 75

REQUEST_TIMEOUT = 25

# الحد الأقصى للنص المستخرج من المقال
MAX_CONTENT_LENGTH = 18000


# ============================================================
# Helpers
# ============================================================

def load_sources():

    with open(
        SOURCES_FILE,
        "r",
        encoding="utf-8"
    ) as f:

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

    text = str(text)

    # إزالة المسافات الزائدة
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


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

    # إزالة الرموز
    title = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        title
    )

    # إزالة كلمات عامة جداً
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
        "قبل"
    }

    words = [
        word
        for word in words
        if word not in stop_words
    ]

    return " ".join(words)


# ============================================================
# RSS
# ============================================================

def get_feed(url):

    try:

        print(
            f"    Trying RSS: {url}"
        )

        feed = feedparser.parse(
            url,
            request_headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "SaudiEconomyDaily/2.0"
            }
        )

        if feed.bozo:

            print(
                "    RSS warning: feed.bozo=True"
            )

        if not feed.entries:

            print(
                "    RSS result: 0 entries"
            )

            return []


        print(
            f"    RSS result: "
            f"{len(feed.entries)} entries"
        )

        return feed.entries


    except Exception as e:

        print(
            f"    RSS ERROR: {e}"
        )

        return []


# ============================================================
# Article extraction
# ============================================================

def extract_article_text(url):

    if not url:

        return ""


    try:

        print(
            "    Extracting article content..."
        )

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
            timeout=REQUEST_TIMEOUT
        )


        if not response.ok:

            print(
                f"    Article HTTP status: "
                f"{response.status_code}"
            )

            return ""


        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )


        # ----------------------------------------------------
        # إزالة العناصر التي ليست من المقال
        # ----------------------------------------------------

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "form",
            "aside"
        ]):

            tag.decompose()


        # ----------------------------------------------------
        # محاولة إيجاد article
        # ----------------------------------------------------

        candidates = []


        article_tags = soup.find_all(
            "article"
        )

        candidates.extend(
            article_tags
        )


        # بعض المواقع تستخدم divs تحتوي article
        candidates.extend(
            soup.find_all(
                "div",
                class_=re.compile(
                    r"article|story|content|post|entry|body",
                    re.I
                )
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


        # ----------------------------------------------------
        # إذا لم نجد article واضح
        # نستخدم body
        # ----------------------------------------------------

        if len(best_text) < 300:

            body = soup.find(
                "body"
            )

            if body:

                best_text = clean_text(
                    body.get_text(
                        " ",
                        strip=True
                    )
                )


        # ----------------------------------------------------
        # تنظيف النص
        # ----------------------------------------------------

        best_text = clean_text(
            best_text
        )


        if len(best_text) < 200:

            print(
                "    Article extraction: "
                "not enough text"
            )

            return ""


        print(
            f"    Article extracted: "
            f"{len(best_text)} characters"
        )


        return best_text[
            :MAX_CONTENT_LENGTH
        ]


    except Exception as e:

        print(
            f"    Article extraction ERROR: {e}"
        )

        return ""


# ============================================================
# RSS Article conversion
# ============================================================

def extract_articles(entries, source):

    articles = []


    for entry in entries[
        :MAX_ARTICLES_PER_SOURCE
    ]:

        title = clean_text(
            entry.get(
                "title",
                ""
            )
        )


        url = clean_text(
            entry.get(
                "link",
                ""
            )
        )


        description = remove_html(
            entry.get(
                "summary",
                ""
            )
        )


        if not title or not url:

            continue


        # ----------------------------------------------------
        # محاولة الحصول على النص الكامل
        # ----------------------------------------------------

        full_content = extract_article_text(
            url
        )


        # إذا فشل استخراج المقال
        # نستخدم RSS summary
        if len(full_content) >= 200:

            content = full_content

        else:

            content = description


        articles.append({

            "id": article_id(
                title,
                url
            ),

            "title": title,

            "url": url,

            "content": content,

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
        source.get(
            "methods",
            []
        )
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
    print(
        f"SOURCE: {name}"
    )
    print("=" * 60)


    # --------------------------------------------------------
    # Direct RSS
    # --------------------------------------------------------

    for method in methods:

        if method.get("type") != "rss":

            continue


        rss_url = method.get(
            "url"
        )


        if not rss_url:

            continue


        entries = get_feed(
            rss_url
        )


        if entries:

            print(
                f"    SUCCESS: "
                f"{name} via RSS"
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


        query = method.get(
            "query"
        )


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
                f"    SUCCESS: "
                f"{name} via Google News"
            )


            return extract_articles(
                entries,
                source
            )


    print(
        f"    FAILED: "
        f"No articles found for {name}"
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
            f"Telegram status: "
            f"{response.status_code}"
        )


        if not response.ok:

            print(
                response.text[:2000]
            )


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

        "oil":
            "النفط والطاقة",

        "markets":
            "الأسواق",

        "banks":
            "البنوك والقطاع المالي",

        "companies":
            "الشركات",

        "investment":
            "الاستثمار",

        "government":
            "الحكومة والأنظمة",

        "real_estate":
            "العقارات",

        "employment":
            "سوق العمل",

        "technology":
            "التقنية",

        "tourism":
            "السياحة",

        "industry":
            "الصناعة",

        "mining":
            "التعدين",

        "transport":
            "النقل والبنية التحتية",

        "economy":
            "الاقتصاد",

        "other":
            "أخرى"
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
        ai.get(
            "headline",
            ""
        )
    )


    summary = clean_text(
        ai.get(
            "summary",
            ""
        )
    )


    why = clean_text(
        ai.get(
            "why_it_matters",
            ""
        )
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

        f"📊 القطاع: "
        f"{category_name}\n"

        f"🔴 الأهمية: "
        f"{importance}/100\n\n"

        f"📰 المصدر: "
        f"{article['source']}\n"

        f"🔗 {article['url']}"
    )


    return message


# ============================================================
# Main
# ============================================================

def main():

    print("")
    print(
        "🇸🇦 Saudi Economy Daily"
    )
    print(
        "Starting AI news collection..."
    )
    print("")


    # --------------------------------------------------------
    # Check files
    # --------------------------------------------------------

    if not os.path.exists(
        SOURCES_FILE
    ):

        print(
            f"ERROR: Sources file not found: "
            f"{SOURCES_FILE}"
        )

        return


    # --------------------------------------------------------
    # Load sources
    # --------------------------------------------------------

    sources = load_sources()


    print(
        f"Enabled sources: "
        f"{len(sources)}"
    )


    all_articles = []

    seen_ids = set()

    seen_titles = set()


    # --------------------------------------------------------
    # Collect news
    # --------------------------------------------------------

    for source in sources:

        try:

            articles = fetch_source(
                source
            )


            for article in articles:

                article_id_value = article[
                    "id"
                ]


                if article_id_value in seen_ids:

                    continue


                # ------------------------------------------------
                # إزالة الأخبار التي لها نفس العنوان تقريباً
                # ------------------------------------------------

                normalized_title = title_key(
                    article["title"]
                )


                if (
                    normalized_title
                    and normalized_title in seen_titles
                ):

                    print(
                        "Skipping duplicate title:"
                    )

                    print(
                        article["title"]
                    )

                    continue


                seen_ids.add(
                    article_id_value
                )


                if normalized_title:

                    seen_titles.add(
                        normalized_title
                    )


                all_articles.append(
                    article
                )


        except Exception as e:

            print(
                f"ERROR while processing "
                f"{source.get('name', 'Unknown')}: "
                f"{e}"
            )


    # --------------------------------------------------------
    # Sort by source priority
    # --------------------------------------------------------

    all_articles.sort(

        key=lambda x:
            x.get(
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
    # AI candidates
    # --------------------------------------------------------

    candidates = all_articles[
        :MAX_AI_ARTICLES
    ]


    print("")

    print(
        f"Sending "
        f"{len(candidates)} "
        f"articles to AI..."
    )

    print("")


    published = 0


    # --------------------------------------------------------
    # Analyze articles
    # --------------------------------------------------------

    for index, article in enumerate(

        candidates,

        start=1
    ):

        print("")

        print(
            "=" * 60
        )

        print(
            f"AI ARTICLE "
            f"{index}/"
            f"{len(candidates)}"
        )

        print(
            f"Title: "
            f"{article['title']}"
        )


        ai_result = analyze_article(
            article
        )


        if not ai_result:

            print(
                "AI failed. "
                "Skipping article."
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
        # Publish
        # ----------------------------------------------------

        if (

            publish is True

            and importance >= PUBLISH_THRESHOLD

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


                # منع الضغط على Telegram
                time.sleep(1)


        else:

            print(
                "❌ AI decided this article "
                "is not important enough."
            )


    # --------------------------------------------------------
    # Finish
    # --------------------------------------------------------

    print("")

    print(
        "=" * 60
    )

    print(
        f"AI articles published: "
        f"{published}"
    )

    print(
        "=" * 60
    )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    main()
