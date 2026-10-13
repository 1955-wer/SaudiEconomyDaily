import os
import json
import time
import requests


APINEX_API_KEY = (os.getenv("APINEX_API_KEY") or "").strip()
API_BASE_URL = (os.getenv("APINEX_BASE_URL") or "https://api.apinex.bond/v1").strip().rstrip("/")
API_URL = API_BASE_URL + "/chat/completions"
MODEL = os.getenv("AI_MODEL", os.getenv("LEGACY_MODEL", "free/glm-5.3-flash")).strip() or "free/glm-5.3-flash"
FALLBACK_MODEL = os.getenv("AI_FALLBACK_MODEL", os.getenv("LEGACY_FALLBACK_MODEL", "free/mimo-v2.6-pro")).strip() or "free/mimo-v2.6-pro"

MAX_RETRIES = 3

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


def arabic_ratio(text):
    text = str(text or "")
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    arabic = sum("\u0600" <= ch <= "\u06ff" for ch in letters)
    return arabic / len(letters)


def analyze_articles(articles):
    if not APINEX_API_KEY:
        print("ERROR: APINEX_API_KEY is missing")
        return {}

    if not articles:
        return {}

    def analyze_one(article, model):
        prepared = {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", ""))[:500],
            "source": str(article.get("source", ""))[:150],
            "source_type": str(article.get("source_type", ""))[:100],
            "default_content_type": str(article.get("default_content_type", "news")),
            "url": str(article.get("url", "")),
            "content": str(article.get("content", ""))[:12000],
        }

        user_prompt = f"""
حلل الخبر التالي واختر هل يستحق النشر في نشرة اقتصادية عن السعودية.
المصدر قد يكون عربياً أو إنجليزياً أو بلغة أخرى.

مهم جداً:
- إذا كان المصدر أو عنوانه أو محتواه بالإنجليزية، يجب أن تكون النتيجة النهائية بالعربية الفصحى: العنوان والملخص و"لماذا يهم" و"أبرز المعلومات" كلها بالعربية.
- لا تمنع الخبر بسبب كون المصدر إنجليزياً.
- اسم المصدر نفسه يجب أن يبقى كما هو، ولا تترجم اسم المصدر.
- لا تترجم أو تغيّر رابط الخبر.
- أسماء الشركات والمؤشرات والجهات العالمية يمكن إبقاؤها بالإنجليزية عند الحاجة داخل نص عربي.
- لا تستخدم أي معلومة غير موجودة في المادة.
- لا تختلق أرقاماً أو تواريخ أو اقتباسات.
- إذا كانت المادة قصيرة، اذكر فقط ما تؤكده.\n- اجعل العنوان محدداً ويذكر الحدث والجهة أو الرقم الأهم متى توفر ذلك، وتجنب العناوين العامة.\n- ميّز بوضوح بين حقيقة وردت في المصدر وتوقع أو رأي منسوب إلى جهة.\n- لا تصف الأثر بأنه إيجابي أو سلبي إلا إذا كان ذلك مدعوماً بالمادة؛ استخدم unknown عند عدم كفاية الدليل.\n- لا تكرر الفكرة نفسها في الملخص وحقائق الخبر، ولا تضف استنتاجاً سببياً غير مثبت.
- الملخص 3 إلى 4 جمل قصيرة وغنية بالمعلومات، مع الأرقام والنسب والتواريخ والأطراف والسياق المباشر المتاح.
- "why_it_matters" من 2 إلى 3 جمل قصيرة.
- "key_facts" من 3 إلى 4 نقاط عند توفرها.

المادة:
{json.dumps(prepared, ensure_ascii=False, indent=2)}

أعد JSON فقط:
{{
  "results": [
    {{
      "id": "{prepared["id"]}",
      "publish": true,
      "importance": 82,
      "confidence": 90,
      "content_type": "news",
      "category": "investment",
      "market_impact": "neutral",
      "headline": "عنوان عربي",
      "summary": "ملخص عربي غني بالمعلومات.",
      "why_it_matters": "أهمية الخبر بالعربية.",
      "affected_entities": ["جهة أو شركة"],
      "key_facts": ["معلومة مهمة", "معلومة مهمة"]
    }}
  ]
}}
"""

        headers = {
            "Authorization": f"Bearer {APINEX_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/1955-wer/SaudiEconomyDaily",
            "X-Title": "Saudi Economy Daily",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + "\n\nإذا كان المصدر إنجليزياً، ترجم المحتوى إلى العربية في الحقول النهائية مع إبقاء اسم المصدر والرابط كما هما."},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 2200,
        }

        rate_limit_wait = 0
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"APInex attempt {attempt}/{MAX_RETRIES} model={model} article={prepared['id']}")
                response = requests.post(
                    API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                print(f"APInex status: {response.status_code}")

                if response.ok:
                    data = response.json()
                    choices = data.get("choices", [])
                    if not choices:
                        print("ERROR: APInex returned no choices")
                    else:
                        text = clean_json_text(
                            choices[0].get("message", {}).get("content", "")
                        )
                        try:
                            parsed = json.loads(text)
                            raw = parsed.get("results", []) if isinstance(parsed, dict) else []
                            if isinstance(raw, list):
                                for item in raw:
                                    normalized = normalize_result(item)
                                    if not normalized:
                                        continue
                                    normalized["id"] = str(article.get("id", ""))
                                    combined = " ".join([
                                        normalized.get("headline", ""),
                                        normalized.get("summary", ""),
                                        normalized.get("why_it_matters", ""),
                                    ])
                                    if arabic_ratio(combined) < 0.45:
                                        print("ERROR: APInex output was not sufficiently Arabic; rejecting result.")
                                        continue
                                    return normalized
                        except json.JSONDecodeError:
                            print("ERROR: APInex returned invalid JSON")
                elif response.status_code in (402, 403, 401, 404, 413):
                    # These are usually account/model/configuration gates, not transient
                    # network failures. Log the provider's diagnostic and move to the
                    # next configured model instead of retrying the same request.
                    print(f"APInex non-retryable account/model error: HTTP {response.status_code}")
                    print(f"APInex diagnostic: {response.text[:1500]}")
                    return None
                elif response.status_code in (429, 500, 502, 503, 504):
                    print(f"APInex transient/limit error: HTTP {response.status_code}")
                    print(f"APInex diagnostic: {response.text[:1000]}")
                    if response.status_code == 429:
                        try:
                            retry_after = int(response.headers.get("Retry-After", "0"))
                        except ValueError:
                            retry_after = 0
                        rate_limit_wait = max(retry_after, 20 * attempt)
                else:
                    print(f"APInex ERROR: HTTP {response.status_code}")
                    print(response.text[:2000])
                    return None

            except requests.Timeout:
                print("APInex request timed out.")
            except requests.RequestException as error:
                print(f"APInex network error: {error}")
            except Exception as error:
                print(f"Unexpected APInex error: {error}")

            if attempt < MAX_RETRIES:
                wait_seconds = rate_limit_wait if rate_limit_wait else attempt * 5
                rate_limit_wait = 0
                print(f"Waiting {wait_seconds}s before retry...")
                time.sleep(min(wait_seconds, 90))

        return None

    results = {}

    # Allow an operator to configure additional APInex model IDs without a
    # code change. Keep the configured primary and fallback first.
    extra_models = [
        item.strip()
        for item in os.getenv("AI_EXTRA_MODELS", os.getenv("LEGACY_EXTRA_MODELS", "")).split(",")
        if item.strip()
    ]
    model_chain = []
    for model in [MODEL, FALLBACK_MODEL, *extra_models]:
        if model and model not in model_chain:
            model_chain.append(model)

    print("AI model chain: " + " -> ".join(model_chain))

    for article in articles:
        result = None
        for index, model in enumerate(model_chain):
            if index:
                print(f"Legacy AI model fallback: {model_chain[index - 1]} -> {model}")
            result = analyze_one(article, model)
            if result:
                break

        if result:
            results[result["id"]] = result

    print(f"AI analysis completed: {len(results)}/{len(articles)} candidate(s).")
    return results


def analyze_article(article):
    results = analyze_articles([article])
    return results.get(str(article.get("id", "")))
