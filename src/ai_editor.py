import os
import json
import time
import requests


# The API key can come from TOKEN_HARBOR_API_KEY or the older APINEX_API_KEY
# secret, so the existing GitHub secret keeps working.
def load_api_keys():
    """Keys may be separated by commas or new lines. The first one that works is used."""
    raw = (
        os.getenv("TOKEN_HARBOR_API_KEYS")
        or os.getenv("TOKEN_HARBOR_API_KEY")
        or os.getenv("APINEX_API_KEY")
        or ""
    )
    keys = []
    for part in raw.replace("\n", ",").split(","):
        key = part.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


API_KEYS = load_api_keys()

API_BASE_URL = (
    os.getenv("TOKEN_HARBOR_BASE_URL")
    or os.getenv("APINEX_BASE_URL")
    or "https://tokenharbor.ai/v1"
).strip().rstrip("/")

API_URL = API_BASE_URL + "/chat/completions"

# Free models on Token Harbor, fixed in code so a leftover AI_MODEL variable
# in GitHub cannot bring back a paid model. Claude Haiku is not free on this account.
MODEL = "deepseek-v4.1-flash:free"
FALLBACK_MODEL = "mimo-v2.6-flash:free"

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

ALLOWED_IMPACTS = {"positive", "negative", "neutral", "mixed", "unknown"}

ALLOWED_TYPES = {"news", "analysis", "report", "data"}


USER_PROMPT_TEMPLATE = """
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
- إذا كانت المادة قصيرة، اذكر فقط ما تؤكده.
- اجعل العنوان محدداً ويذكر الحدث والجهة أو الرقم الأهم متى توفر ذلك، وتجنب العناوين العامة.
- ميّز بوضوح بين حقيقة وردت في المصدر وتوقع أو رأي منسوب إلى جهة.
- لا تصف الأثر بأنه إيجابي أو سلبي إلا إذا كان ذلك مدعوماً بالمادة؛ استخدم unknown عند عدم كفاية الدليل.
- لا تكرر الفكرة نفسها في الملخص وحقائق الخبر، ولا تضف استنتاجاً سببياً غير مثبت.
- الملخص 3 إلى 4 جمل قصيرة وغنية بالمعلومات، مع الأرقام والنسب والتواريخ والأطراف والسياق المباشر المتاح.
- "why_it_matters" من 2 إلى 3 جمل قصيرة.
- "key_facts" من 3 إلى 4 نقاط عند توفرها.

المادة:
{article_json}

أعد JSON فقط:
{{
  "results": [
    {{
      "id": "{article_id}",
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

    entities = [str(x).strip() for x in entities if str(x).strip()][:6]
    facts = [str(x).strip() for x in facts if str(x).strip()][:4]

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
    if not API_KEYS:
        print("ERROR: no API key found (TOKEN_HARBOR_API_KEYS, TOKEN_HARBOR_API_KEY or APINEX_API_KEY)")
        return {}

    if not articles:
        return {}

    print(f"API keys configured: {len(API_KEYS)}")

    def analyze_one(article, model, key_number, api_key):
        """Returns (result, next_step). next_step is 'model', 'key', or None."""
        prepared = {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", ""))[:500],
            "source": str(article.get("source", ""))[:150],
            "source_type": str(article.get("source_type", ""))[:100],
            "default_content_type": str(article.get("default_content_type", "news")),
            "url": str(article.get("url", "")),
            "content": str(article.get("content", ""))[:12000],
        }

        user_prompt = USER_PROMPT_TEMPLATE.format(
            article_json=json.dumps(prepared, ensure_ascii=False, indent=2),
            article_id=prepared["id"],
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
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
        json_retry_used = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"TokenHarbor attempt {attempt}/{MAX_RETRIES} model={model} key=#{key_number} article={prepared['id']}")

                response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
                print(f"TokenHarbor status: {response.status_code} (key #{key_number})")

                if response.ok:
                    data = response.json()
                    choices = data.get("choices", [])

                    if not choices:
                        print("ERROR: TokenHarbor returned no choices")
                        return None, "model"

                    text = clean_json_text(choices[0].get("message", {}).get("content", ""))

                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        print("ERROR: TokenHarbor returned invalid JSON")
                        if json_retry_used:
                            return None, "model"
                        json_retry_used = True
                        print("Retrying once for invalid JSON...")
                        continue

                    raw = parsed.get("results", []) if isinstance(parsed, dict) else []

                    for item in raw if isinstance(raw, list) else []:
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
                            print("ERROR: output was not sufficiently Arabic; rejecting result.")
                            continue

                        return normalized, None

                    return None, "model"

                elif response.status_code in (401, 402, 403):
                    # Bad key, exhausted key, or key not allowed for this model.
                    # Another key may still work.
                    print(f"TokenHarbor key error: HTTP {response.status_code}")
                    print(f"TokenHarbor diagnostic: {response.text[:800]}")
                    return None, "key"

                elif response.status_code in (404, 413):
                    # Model not found or payload too large: another key will not help.
                    print(f"TokenHarbor model/payload error: HTTP {response.status_code}")
                    print(f"TokenHarbor diagnostic: {response.text[:800]}")
                    return None, "model"

                elif response.status_code == 429:
                    print("TokenHarbor rate limit: HTTP 429")
                    print(f"TokenHarbor diagnostic: {response.text[:500]}")
                    try:
                        retry_after = int(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        retry_after = 0
                    rate_limit_wait = max(retry_after, 20 * attempt)

                elif response.status_code in (500, 502, 503, 504):
                    print(f"TokenHarbor server error: HTTP {response.status_code}")
                    print(f"TokenHarbor diagnostic: {response.text[:500]}")

                else:
                    print(f"TokenHarbor unexpected error: HTTP {response.status_code}")
                    print(response.text[:800])
                    return None, "model"

            except requests.Timeout:
                print("TokenHarbor request timed out.")
            except requests.RequestException as error:
                print(f"TokenHarbor network error: {error}")
            except Exception as error:
                print(f"Unexpected TokenHarbor error: {error}")

            if attempt < MAX_RETRIES:
                wait_seconds = rate_limit_wait if rate_limit_wait else attempt * 5
                rate_limit_wait = 0
                print(f"Waiting {wait_seconds}s before retry...")
                time.sleep(min(wait_seconds, 90))

        # Retries exhausted: a rate limit may clear with another key; otherwise
        # the problem is more likely this model/request, so move on.
        return None, ("key" if rate_limit_wait else "model")

    results = {}

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

        for model_index, model in enumerate(model_chain):
            if model_index:
                print(f"Model fallback -> {model}")

            for key_index, api_key in enumerate(API_KEYS, start=1):
                if key_index > 1:
                    print(f"Key fallback -> key #{key_index}")

                result, next_step = analyze_one(article, model, key_index, api_key)

                if result or next_step == "model":
                    break

            if result:
                break

        if result:
            results[result["id"]] = result

    print(f"AI analysis completed: {len(results)}/{len(articles)} candidate(s).")
    return results


def analyze_article(article):
    results = analyze_articles([article])
    return results.get(str(article.get("id", "")))
