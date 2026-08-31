import os
import json
import time
import requests


# ============================================================
# OpenRouter Configuration
# ============================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# الموديل الأساسي
MODEL = "inclusionai/ling-3.0-flash-fin:free"

# عدد المحاولات عند حدوث خطأ مؤقت
MAX_RETRIES = 3

# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
أنت محرر اقتصادي محترف ومتخصص في الاقتصاد السعودي.

مهمتك تحليل الأخبار التي تصل إليك وتحديد هل تستحق النشر في قناة
Saudi Economy Daily أم لا.

القناة متخصصة في الأخبار الاقتصادية السعودية.

ركز على الأخبار التي لها تأثير حقيقي على:

- الاقتصاد السعودي
- النفط والطاقة
- أرامكو
- البنوك والقطاع المالي
- سوق الأسهم السعودي
- الشركات السعودية الكبرى
- الاستثمار
- المشاريع الكبرى
- رؤية السعودية 2030
- الميزانية السعودية
- التضخم
- أسعار الفائدة
- التجارة
- العقارات
- الوظائف وسوق العمل
- الأنظمة والقرارات الاقتصادية
- الناتج المحلي
- السياحة
- الصناعة
- التعدين
- النقل والبنية التحتية
- الاستثمارات الأجنبية

تجاهل الأخبار الصغيرة أو العادية التي لا تحمل أهمية اقتصادية حقيقية.

قواعد مهمة جداً:

1. لا تخترع أي معلومة.
2. لا تخترع أي رقم.
3. لا تغير الأرقام الموجودة في الخبر.
4. لا تضف معلومات من معرفتك السابقة.
5. استخدم المعلومات الموجودة في الخبر فقط.
6. إذا كانت المعلومة غير موجودة، لا تذكرها.
7. إذا كان الخبر غير واضح أو ناقصاً، اجعل publish=false.
8. إذا كان الخبر مجرد إعلان عادي أو خبر غير اقتصادي، اجعل publish=false.
9. لا تعتبر كل خبر عن السعودية خبراً اقتصادياً.
10. الأهمية يجب أن تعكس التأثير الاقتصادي الحقيقي على السعودية.
11. اكتب بالعربية الفصحى الواضحة.
12. اجعل الملخص مختصراً ومفيداً.
13. لا تستخدم مبالغات مثل "تاريخي" أو "ضخم" إلا إذا كان الخبر نفسه يثبت ذلك.

درجات الأهمية:

0-49   = غير مهم
50-69  = منخفض
70-84  = مهم
85-94  = مهم جداً
95-100 = عاجل / شديد الأهمية

إذا كان الخبر يستحق النشر:

publish=true

إذا لم يكن يستحق النشر:

publish=false

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
"""


# ============================================================
# Helpers
# ============================================================

def clean_json_text(text):
    """
    تنظيف إجابة الذكاء الاصطناعي إذا أضاف Markdown أو نصاً حول JSON.
    """

    if not text:
        return ""

    text = text.strip()

    # إزالة Markdown code fences
    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```JSON", "")
        text = text.replace("```", "")
        text = text.strip()

    # محاولة استخراج أول { وآخر }
    first = text.find("{")
    last = text.rfind("}")

    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    return text.strip()


def validate_result(result):
    """
    التأكد من أن نتيجة AI تحتوي على الحقول المطلوبة.
    """

    if not isinstance(result, dict):
        return None

    publish = result.get("publish", False)

    if not isinstance(publish, bool):
        publish = False

    try:
        importance = int(result.get("importance", 0))
    except Exception:
        importance = 0

    importance = max(0, min(100, importance))

    category = result.get("category", "other")

    allowed_categories = {
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
        "other"
    }

    if category not in allowed_categories:
        category = "other"

    headline = str(result.get("headline", "")).strip()
    summary = str(result.get("summary", "")).strip()
    why = str(result.get("why_it_matters", "")).strip()

    key_facts = result.get("key_facts", [])

    if not isinstance(key_facts, list):
        key_facts = []

    key_facts = [
        str(item).strip()
        for item in key_facts
        if str(item).strip()
    ][:5]

    # إذا كانت البيانات ناقصة، لا ننشر
    if not headline or not summary:
        publish = False

    return {
        "publish": publish,
        "importance": importance,
        "category": category,
        "headline": headline,
        "summary": summary,
        "why_it_matters": why,
        "key_facts": key_facts
    }


# ============================================================
# AI Analysis
# ============================================================

def analyze_article(article):

    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing")
        return None

    title = str(article.get("title", "")).strip()
    source = str(article.get("source", "")).strip()
    url = str(article.get("url", "")).strip()
    content = str(article.get("content", "")).strip()

    if not content:
        content = title

    # لا نرسل نصاً ضخماً جداً
    content = content[:18000]

    user_prompt = f"""
حلل الخبر التالي.

المصدر:
{source}

العنوان:
{title}

الرابط:
{url}

محتوى الخبر:
{content}

مهم:

اعتمد فقط على المعلومات الموجودة في العنوان ومحتوى الخبر.

لا تستخدم معلومات خارجية.

أريد النتيجة باللغة العربية.
"""


    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/1955-wer/SaudiEconomyDaily",
        "X-OpenRouter-Title": "Saudi Economy Daily"
    }


    payload = {
        "model": MODEL,

        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],

        "temperature": 0.1,

        "max_tokens": 900,

        "response_format": {
            "type": "json_object"
        }
    }


    for attempt in range(1, MAX_RETRIES + 1):

        try:

            print(
                f"OpenRouter attempt {attempt}/{MAX_RETRIES}"
            )

            response = requests.post(
                API_URL,
                headers=headers,
                json=payload,
                timeout=90
            )

            print(
                f"OpenRouter status: {response.status_code}"
            )


            # ------------------------------------------------
            # Success
            # ------------------------------------------------

            if response.ok:

                data = response.json()

                choices = data.get("choices", [])

                if not choices:

                    print("ERROR: OpenRouter returned no choices")

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                message = choices[0].get("message", {})

                result_text = message.get(
                    "content",
                    ""
                )

                if not result_text:

                    print("ERROR: AI returned empty content")

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                result_text = clean_json_text(
                    result_text
                )


                try:

                    result = json.loads(
                        result_text
                    )

                except json.JSONDecodeError:

                    print(
                        "ERROR: AI returned invalid JSON"
                    )

                    print(
                        result_text[:3000]
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                validated = validate_result(
                    result
                )

                if validated is None:

                    print(
                        "ERROR: AI result validation failed"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                return validated


            # ------------------------------------------------
            # Rate limit
            # ------------------------------------------------

            if response.status_code == 429:

                print(
                    "OpenRouter rate limit reached."
                )

                if attempt < MAX_RETRIES:

                    wait_time = attempt * 5

                    print(
                        f"Waiting {wait_time} seconds..."
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                return None


            # ------------------------------------------------
            # Temporary server errors
            # ------------------------------------------------

            if response.status_code >= 500:

                print(
                    "OpenRouter server error:"
                )

                print(
                    response.text[:2000]
                )

                if attempt < MAX_RETRIES:

                    wait_time = attempt * 5

                    time.sleep(
                        wait_time
                    )

                    continue

                return None


            # ------------------------------------------------
            # Other errors
            # ------------------------------------------------

            print(
                "OpenRouter ERROR:"
            )

            print(
                response.text[:3000]
            )

            return None


        except requests.Timeout:

            print(
                "OpenRouter request timed out."
            )

            if attempt < MAX_RETRIES:

                time.sleep(3)
                continue

            return None


        except requests.RequestException as e:

            print(
                f"OpenRouter network error: {e}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(3)
                continue

            return None


        except Exception as e:

            print(
                f"Unexpected AI error: {e}"
            )

            return None


    return None

