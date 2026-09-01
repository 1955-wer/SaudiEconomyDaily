import os
import json
import time
import requests


# ============================================================
# OpenRouter Configuration
# ============================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "inclusionai/ling-3.0-flash-fin:free"

MAX_RETRIES = 2


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
أنت رئيس تحرير اقتصادي متخصص في الاقتصاد السعودي.

تعمل لصالح قناة:
Saudi Economy Daily

مهمتك تحليل مجموعة من الأخبار وتحديد:
1. هل الخبر اقتصادي ومهم للسعودية؟
2. هل يستحق النشر؟
3. ما درجة أهميته؟
4. ما درجة الثقة في التحليل؟
5. ما القطاع؟
6. ما الأثر المحتمل؟
7. ما الجهات المتأثرة؟
8. ما أهم الحقائق والأرقام؟
9. لماذا يهم الخبر؟

قواعد التحرير:

- لا تخترع أي معلومة.
- لا تخترع أي رقم.
- لا تغير الأرقام.
- لا تستخدم معلومات خارج النص المقدم.
- إذا كان الخبر صفحة معلومات، سعر سهم، شاشة تداول، ملف شركة، أو قائمة عامة، لا تنشره.
- إذا كان الخبر غير متعلق بالاقتصاد السعودي أو أثره على السعودية ضعيفاً، لا تنشره.
- لا تعتبر مجرد ذكر السعودية سبباً كافياً للنشر.
- لا تبالغ في التأثير.
- استخدم العربية الفصحى الواضحة.
- اجعل العنوان مختصراً.
- اجعل الملخص دقيقاً ومفيداً.
- لا تستخدم لغة تسويقية أو مبالغات.

معايير الأهمية:

0-49   غير مهم
50-69  منخفض
70-84  مهم
85-94  مهم جداً
95-100 عاجل / شديد الأهمية

التصنيفات المسموحة فقط:

oil
markets
banks
companies
investment
government
real_estate
employment
technology
tourism
industry
mining
transport
economy
other

market_impact المسموح:

positive
negative
neutral
mixed
unknown

publish=true فقط عندما يكون الخبر ذا قيمة حقيقية لقارئ اقتصادي يهتم بالسعودية.

أعد JSON صحيحاً فقط، بدون Markdown وبدون أي نص خارج JSON.

الإجابة يجب أن تكون كائن JSON بهذا الشكل:

{
  "results": [
    {
      "id": "رقم الخبر",
      "publish": true,
      "importance": 87,
      "confidence": 92,
      "category": "investment",
      "market_impact": "positive",
      "headline": "عنوان مختصر",
      "summary": "ملخص دقيق",
      "why_it_matters": "لماذا يهم",
      "affected_entities": ["اسم جهة أو شركة"],
      "key_facts": ["معلومة مهمة", "رقم مهم"]
    }
  ]
}
"""


ALLOWED_CATEGORIES = {
    "oil",
    "markets",
    "banks",
    "companies",
    "investment",
    "government",
    "real_estate",
    "employment",
    "technology",
    "tourism",
    "industry",
    "mining",
    "transport",
    "economy",
    "other",
}

ALLOWED_IMPACTS = {
    "positive",
    "negative",
    "neutral",
    "mixed",
    "unknown",
}


# ============================================================
# JSON Helpers
# ============================================================

def clean_json_text(text):
    if not text:
        return ""

    text = text.strip()

    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```JSON"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    first = text.find("{")
    last = text.rfind("}")

    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    return text.strip()


def normalize_result(item, article_id):
    if not isinstance(item, dict):
        return None

    publish = item.get("publish", False)
    if not isinstance(publish, bool):
        publish = False

    try:
        importance = int(item.get("importance", 0))
    except Exception:
        importance = 0
    importance = max(0, min(100, importance))

    try:
        confidence = int(item.get("confidence", 0))
    except Exception:
        confidence = 0
    confidence = max(0, min(100, confidence))

    category = item.get("category", "other")
    if category not in ALLOWED_CATEGORIES:
        category = "other"

    market_impact = item.get("market_impact", "unknown")
    if market_impact not in ALLOWED_IMPACTS:
        market_impact = "unknown"

    headline = str(item.get("headline", "")).strip()
    summary = str(item.get("summary", "")).strip()
    why = str(item.get("why_it_matters", "")).strip()

    affected_entities = item.get("affected_entities", [])
    if not isinstance(affected_entities, list):
        affected_entities = []
    affected_entities = [
        str(x).strip()
        for x in affected_entities
        if str(x).strip()
    ][:8]

    key_facts = item.get("key_facts", [])
    if not isinstance(key_facts, list):
        key_facts = []
    key_facts = [
        str(x).strip()
        for x in key_facts
        if str(x).strip()
    ][:5]

    if not headline or not summary:
        publish = False

    return {
        "id": str(article_id),
        "publish": publish,
        "importance": importance,
        "confidence": confidence,
        "category": category,
        "market_impact": market_impact,
        "headline": headline,
        "summary": summary,
        "why_it_matters": why,
        "affected_entities": affected_entities,
        "key_facts": key_facts,
    }


# ============================================================
# Batch Analysis
# ============================================================

def analyze_articles(articles):
    """
    Analyze several articles in one OpenRouter request.
    This greatly reduces API calls compared with one request per article.
    """

    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing")
        return {}

    if not articles:
        return {}

    prepared = []

    for index, article in enumerate(articles, start=1):
        article_id = str(article.get("id", index))
        title = str(article.get("title", "")).strip()
        source = str(article.get("source", "")).strip()
        url = str(article.get("url", "")).strip()
        content = str(article.get("content", "")).strip()

        if not content:
            content = title

        prepared.append(
            {
                "id": article_id,
                "title": title,
                "source": source,
                "url": url,
                "content": content[:9000],
            }
        )

    user_prompt = f"""
حلل كل الأخبار التالية.

مهم جداً:
- يجب أن تعيد نتيجة واحدة لكل id.
- لا تحذف أي id.
- لا تستخدم معلومات خارج النص.
- لا تعتبر وجود كلمة "السعودية" وحده كافياً للنشر.
- أعط أولوية للأخبار الاقتصادية السعودية الحقيقية.

الأخبار:

{json.dumps(prepared, ensure_ascii=False, indent=2)}

أعد JSON واحداً فقط:
{{
  "results": [
    {{
      "id": "نفس id",
      "publish": false,
      "importance": 0,
      "confidence": 0,
      "category": "other",
      "market_impact": "unknown",
      "headline": "",
      "summary": "",
      "why_it_matters": "",
      "affected_entities": [],
      "key_facts": []
    }}
  ]
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/1955-wer/SaudiEconomyDaily",
        "X-OpenRouter-Title": "Saudi Economy Daily",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "temperature": 0.1,
        "max_tokens": 5000,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"OpenRouter batch attempt {attempt}/{MAX_RETRIES}")
            print(f"Batch size: {len(articles)} articles")

            response = requests.post(
                API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )

            print(f"OpenRouter status: {response.status_code}")

            if response.ok:
                data = response.json()
                choices = data.get("choices", [])

                if not choices:
                    print("ERROR: OpenRouter returned no choices")
                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue
                    return {}

                content = choices[0].get("message", {}).get("content", "")

                if not content:
                    print("ERROR: AI returned empty content")
                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue
                    return {}

                content = clean_json_text(content)

                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    print("ERROR: AI returned invalid JSON")
                    print(content[:5000])
                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue
                    return {}

                raw_results = parsed.get("results", [])

                if not isinstance(raw_results, list):
                    print("ERROR: AI results is not a list")
                    return {}

                normalized = {}

                for item in raw_results:
                    item_id = str(item.get("id", "")).strip()

                    if not item_id:
                        continue

                    result = normalize_result(item, item_id)

                    if result:
                        normalized[item_id] = result

                # Ensure every requested article has a result.
                # Missing results become non-publishable rather than silently passing.
                for article in articles:
                    aid = str(article.get("id", ""))

                    if aid not in normalized:
                        normalized[aid] = {
                            "id": aid,
                            "publish": False,
                            "importance": 0,
                            "confidence": 0,
                            "category": "other",
                            "market_impact": "unknown",
                            "headline": "",
                            "summary": "",
                            "why_it_matters": "",
                            "affected_entities": [],
                            "key_facts": [],
                        }

                return normalized

            if response.status_code == 429:
                print("OpenRouter rate limit reached.")
                if attempt < MAX_RETRIES:
                    time.sleep(attempt * 5)
                    continue
                return {}

            if response.status_code >= 500:
                print("OpenRouter server error:")
                print(response.text[:3000])

                if attempt < MAX_RETRIES:
                    time.sleep(attempt * 5)
                    continue
                return {}

            print("OpenRouter ERROR:")
            print(response.text[:3000])
            return {}

        except requests.Timeout:
            print("OpenRouter request timed out.")

            if attempt < MAX_RETRIES:
                time.sleep(3)
                continue

            return {}

        except requests.RequestException as error:
            print(f"OpenRouter network error: {error}")

            if attempt < MAX_RETRIES:
                time.sleep(3)
                continue

            return {}

        except Exception as error:
            print(f"Unexpected AI error: {error}")
            return {}

    return {}


def analyze_article(article):
    """
    Compatibility wrapper for code that still analyzes one article.
    """
    results = analyze_articles([article])
    return results.get(str(article.get("id", "")))
