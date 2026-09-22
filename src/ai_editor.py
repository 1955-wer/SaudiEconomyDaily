import os
import json
import time
import requests


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "inclusionai/ling-3.0-flash-fin:free"

MAX_RETRIES = 2

SYSTEM_PROMPT = """
أنت محرر اقتصادي لقناة Saudi Economy Daily.

حلل مجموعة أخبار ومقالات وتقارير اقتصادية عن السعودية أو ذات أثر مباشر عليها.
لا تكتب مقالة طويلة، لكن لا تختصر الخبر اختصاراً يضيع المعلومات المهمة.
الهدف هو تقديم ملخص اقتصادي غني بالمعلومات، واضح ومناسب للقراءة في Telegram.

لكل عنصر:
- حدد نوع المحتوى: news أو analysis أو report أو data.
- قرر هل يستحق النشر.
- أعطه درجة أهمية من 0 إلى 100.
- أعطه درجة ثقة من 0 إلى 100.
- اكتب ملخصاً من 3 إلى 4 جمل قصيرة عند توفر المعلومات الكافية.
- يجب أن يتضمن الملخص أهم تفاصيل الخبر: ماذا حدث، من الأطراف المعنية، الأرقام والقيم والنسب والتواريخ، وما السياق المباشر للخبر.
- إذا كان الخبر يحتوي على مقارنة أو ترتيب أو تغير زمني، اذكر المقارنة أو اتجاه التغير بوضوح.
- اذكر لماذا يهم في 2 إلى 3 جمل قصيرة، مع توضيح الأثر الاقتصادي المباشر أو القطاعي عندما يسمح النص بذلك.
- استخرج أهم 3 إلى 4 معلومات مؤكدة من النص عند توفرها.
- اذكر الجهات أو الشركات أو القطاعات المتأثرة عند وضوحها.
- لا تخترع أي رقم أو معلومة.
- لا تستخدم معلومات خارج النص.
- لا تعتبر مجرد ذكر السعودية سبباً للنشر.
إذا كان النص الأصلي قصيراً ولا يحتوي إلا على معلومة واحدة مؤكدة، لا تحاول اختراع تفاصيل إضافية؛ عندها استخدم فقط ما يدعمه المصدر.
إذا كان النص غنياً بالمعلومات، استخرج تفاصيله الأساسية بدلاً من اختصاره إلى جملة واحدة.
- تجاهل صفحات معلومات الشركات، لوحات الأسعار، القوائم العامة، الأخبار غير الاقتصادية، والمحتوى المكرر.

نشر الخبر أو المقال:
publish=true عندما تكون له قيمة حقيقية لقارئ مهتم بالاقتصاد السعودي.

الأهمية:
0-49 غير مهم
50-69 منخفض
70-84 مهم
85-94 مهم جداً
95-100 عاجل جداً

التصنيفات:
oil, markets, banks, companies, investment, government,
real_estate, employment, technology, tourism, industry, mining,
transport, economy, other

market_impact:
positive, negative, neutral, mixed, unknown

أعد JSON فقط بالشكل:

{
  "results": [
    {
      "id": "id",
      "publish": true,
      "importance": 82,
      "confidence": 90,
      "content_type": "analysis",
      "category": "investment",
      "market_impact": "neutral",
      "headline": "عنوان مختصر",
      "summary": "ملخص غني بالمعلومات من 3 إلى 4 جمل قصيرة، يتضمن التفاصيل والأرقام والسياق المتاح في المصدر.",
      "why_it_matters": "توضيح من 2 إلى 3 جمل قصيرة لأهمية الخبر وأثره الاقتصادي المباشر أو القطاعي.",
      "affected_entities": ["جهة أو شركة", "جهة أو شركة"],
      "key_facts": ["معلومة أو رقم مهم", "معلومة مهمة", "معلومة مهمة", "معلومة مهمة"]
    }
  ]
}
"""

ALLOWED_CATEGORIES = {
    "oil", "markets", "banks", "companies", "investment",
    "government", "real_estate", "employment", "technology",
    "tourism", "industry", "mining", "transport", "economy", "other"
}

ALLOWED_IMPACTS = {
    "positive", "negative", "neutral", "mixed", "unknown"
}

ALLOWED_TYPES = {
    "news", "analysis", "report", "data"
}


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


def normalize_result(item):
    if not isinstance(item, dict):
        return None

    article_id = str(item.get("id", "")).strip()
    if not article_id:
        return None

    publish = item.get("publish", False)
    if not isinstance(publish, bool):
        publish = False

    try:
        importance = int(item.get("importance", 0))
    except Exception:
        importance = 0

    try:
        confidence = int(item.get("confidence", 0))
    except Exception:
        confidence = 0

    importance = max(0, min(100, importance))
    confidence = max(0, min(100, confidence))

    content_type = item.get("content_type", "news")
    if content_type not in ALLOWED_TYPES:
        content_type = "news"

    category = item.get("category", "other")
    if category not in ALLOWED_CATEGORIES:
        category = "other"

    impact = item.get("market_impact", "unknown")
    if impact not in ALLOWED_IMPACTS:
        impact = "unknown"

    headline = str(item.get("headline", "")).strip()
    summary = str(item.get("summary", "")).strip()
    why = str(item.get("why_it_matters", "")).strip()

    entities = item.get("affected_entities", [])
    if not isinstance(entities, list):
        entities = []

    facts = item.get("key_facts", [])
    if not isinstance(facts, list):
        facts = []

    entities = [
        str(x).strip()
        for x in entities
        if str(x).strip()
    ][:6]

    facts = [
        str(x).strip()
        for x in facts
        if str(x).strip()
    ][:4]

    if not headline or not summary:
        publish = False

    return {
        "id": article_id,
        "publish": publish,
        "importance": importance,
        "confidence": confidence,
        "content_type": content_type,
        "category": category,
        "market_impact": impact,
        "headline": headline,
        "summary": summary,
        "why_it_matters": why,
        "affected_entities": entities,
        "key_facts": facts,
    }


def analyze_articles(articles):
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing")
        return {}

    if not articles:
        return {}

    prepared = []

    for article in articles:
        prepared.append({
            "id": str(article.get("id", "")),
            "title": str(article.get("title", ""))[:500],
            "source": str(article.get("source", ""))[:150],
            "source_type": str(article.get("source_type", ""))[:100],
            "default_content_type": str(article.get("default_content_type", "news")),
            "url": str(article.get("url", "")),
            "content": str(article.get("content", ""))[:12000],
        })

    user_prompt = f"""
حلل العناصر التالية واختر منها ما يصلح لنشرة اقتصادية.
نريد ملخصاً غنياً بالمعلومات لكنه ليس مقالة طويلة.
استخرج أكبر قدر ممكن من المعلومات المهمة الموجودة فعلاً في النص، خصوصاً الأرقام والقيم والنسب والتواريخ والأطراف والسياق المباشر.
لا تكرر المعلومة نفسها بصيغ مختلفة، ولا تضف أي معلومة غير موجودة في المادة.

العناصر:
{json.dumps(prepared, ensure_ascii=False, indent=2)}

أعد نتيجة لكل id موجود.
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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 5200,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"OpenRouter attempt {attempt}/{MAX_RETRIES}")
            print(f"Batch size: {len(articles)}")

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

                text = choices[0].get("message", {}).get("content", "")
                text = clean_json_text(text)

                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    print("ERROR: AI returned invalid JSON")
                    print(text[:4000])
                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue
                    return {}

                results = {}
                raw = parsed.get("results", [])

                if isinstance(raw, list):
                    for item in raw:
                        normalized = normalize_result(item)
                        if normalized:
                            results[normalized["id"]] = normalized

                return results

            if response.status_code == 429:
                print("OpenRouter rate limit reached.")
                if attempt < MAX_RETRIES:
                    time.sleep(attempt * 5)
                    continue
                return {}

            if response.status_code >= 500:
                print("OpenRouter server error:")
                print(response.text[:2000])
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
    results = analyze_articles([article])
    return results.get(str(article.get("id", "")))
