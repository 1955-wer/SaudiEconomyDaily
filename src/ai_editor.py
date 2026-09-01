import os
import json
import time
import requests


# ============================================================
# OpenRouter
# ============================================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODEL = "inclusionai/ling-3.0-flash-fin:free"

MAX_RETRIES = 3


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """
أنت رئيس تحرير اقتصادي متخصص في الاقتصاد السعودي.

تعمل لصالح قناة إخبارية اسمها:
Saudi Economy Daily

مهمتك ليست فقط تلخيص الخبر، بل تقييم أهميته الاقتصادية وتحديد هل
يستحق النشر أم لا.

============================================================
أولاً: ما الذي يعتبر خبراً مهماً؟
============================================================

ركز على الأخبار التي قد تؤثر على:

- الاقتصاد السعودي
- الناتج المحلي
- النمو الاقتصادي
- النفط والطاقة
- أرامكو
- أوبك+
- أسعار النفط
- البنوك
- أسعار الفائدة
- السيولة
- التضخم
- سوق الأسهم السعودي
- تاسي
- الشركات المدرجة
- الأرباح والنتائج المالية
- الصفقات والاستحواذات
- الاستثمارات
- الاستثمار الأجنبي
- صندوق الاستثمارات العامة
- المشاريع الكبرى
- رؤية السعودية 2030
- الميزانية
- الدين الحكومي
- الصكوك والسندات
- التجارة
- الصادرات والواردات
- العقارات
- السياحة
- الصناعة
- التعدين
- اللوجستيات
- البنية التحتية
- سوق العمل
- التوطين
- التقنية والاقتصاد الرقمي
- القرارات والأنظمة ذات الأثر الاقتصادي

============================================================
ثانياً: ما الذي يجب تجاهله؟
============================================================

اجعل publish=false إذا كان المحتوى:

- مجرد صفحة معلومات لشركة
- صفحة أسعار أو شاشة سوق
- قائمة أخبار عامة بدون خبر فعلي
- إعلاناً بسيطاً لا يحمل أثراً اقتصادياً مهماً
- خبراً اجتماعياً أو رياضياً أو ثقافياً
- خبراً تقنياً بلا أثر واضح على الاقتصاد السعودي
- خبراً عن دولة أخرى دون أثر واضح على السعودية
- خبراً مكرراً أو قديماً
- خبراً قصيراً جداً أو ناقص المعلومات
- عنواناً مضللاً أو لا يحتوي مادة إخبارية واضحة

============================================================
ثالثاً: قواعد الدقة
============================================================

1. لا تخترع أي معلومة.
2. لا تخترع أي رقم.
3. لا تغير الأرقام.
4. لا تستخدم معلومات من خارج الخبر.
5. لا تستخدم معرفتك السابقة لإكمال البيانات.
6. إذا لم يذكر الخبر معلومة، اعتبرها غير معروفة.
7. إذا كان النص ضعيفاً، خفض الثقة.
8. إذا لم يكن الخبر متعلقاً بالاقتصاد السعودي بدرجة كافية، لا تنشره.
9. لا تبالغ في التأثير.
10. لا تستخدم لغة تسويقية.
11. لا تعتبر مجرد ذكر السعودية سبباً كافياً للنشر.

============================================================
رابعاً: الأهمية
============================================================

0-49:
غير مهم

50-69:
منخفض

70-84:
مهم

85-94:
مهم جداً

95-100:
عاجل / شديد الأهمية

============================================================
خامساً: طريقة التفكير
============================================================

قيّم:

1. حجم الأثر الاقتصادي.
2. عدد الجهات أو الشركات المتأثرة.
3. هل توجد أرقام أو نتائج مالية؟
4. هل القرار حكومي أو تنظيمي؟
5. هل الخبر يتعلق بالنفط أو البنوك أو السوق؟
6. هل الخبر متعلق بمشروع أو استثمار كبير؟
7. هل التأثير قصير الأجل أم طويل الأجل؟
8. هل الخبر جديد؟
9. هل الخبر يستحق انتباه المستثمر أو القارئ الاقتصادي؟

============================================================
سادساً: التصنيفات
============================================================

استخدم واحداً فقط:

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

============================================================
سابعاً: تحليل التأثير
============================================================

market_impact يجب أن يكون أحد:

positive
negative
neutral
mixed
unknown

============================================================
ثامناً: القرار
============================================================

publish=true فقط إذا كان الخبر يستحق فعلاً الظهور في قناة
اقتصادية سعودية.

لا تجعل كل الأخبار publish=true.

============================================================
التنسيق
============================================================

أعد JSON فقط.

لا تكتب Markdown.

لا تكتب مقدمة.

لا تكتب ```json.

استخدم هذا الشكل:

{
  "publish": true,
  "importance": 87,
  "confidence": 92,
  "category": "investment",
  "market_impact": "positive",
  "headline": "عنوان مختصر وواضح",
  "summary": "ملخص دقيق ومختصر",
  "why_it_matters": "سبب أهمية الخبر اقتصادياً",
  "affected_entities": [
    "اسم شركة أو جهة"
  ],
  "key_facts": [
    "معلومة مهمة",
    "رقم مهم"
  ]
}
"""


# ============================================================
# Clean JSON
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


# ============================================================
# Validate result
# ============================================================

def validate_result(result):

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

    try:
        confidence = int(result.get("confidence", 0))
    except Exception:
        confidence = 0

    confidence = max(0, min(100, confidence))

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

    category = result.get("category", "other")

    if category not in allowed_categories:
        category = "other"

    allowed_impacts = {
        "positive",
        "negative",
        "neutral",
        "mixed",
        "unknown"
    }

    market_impact = result.get(
        "market_impact",
        "unknown"
    )

    if market_impact not in allowed_impacts:
        market_impact = "unknown"

    headline = str(
        result.get("headline", "")
    ).strip()

    summary = str(
        result.get("summary", "")
    ).strip()

    why_it_matters = str(
        result.get("why_it_matters", "")
    ).strip()

    affected_entities = result.get(
        "affected_entities",
        []
    )

    if not isinstance(
        affected_entities,
        list
    ):
        affected_entities = []

    affected_entities = [
        str(x).strip()
        for x in affected_entities
        if str(x).strip()
    ][:8]

    key_facts = result.get(
        "key_facts",
        []
    )

    if not isinstance(
        key_facts,
        list
    ):
        key_facts = []

    key_facts = [
        str(x).strip()
        for x in key_facts
        if str(x).strip()
    ][:5]

    if not headline or not summary:
        publish = False

    return {
        "publish": publish,
        "importance": importance,
        "confidence": confidence,
        "category": category,
        "market_impact": market_impact,
        "headline": headline,
        "summary": summary,
        "why_it_matters": why_it_matters,
        "affected_entities": affected_entities,
        "key_facts": key_facts
    }


# ============================================================
# Analyze article
# ============================================================

def analyze_article(article):

    if not OPENROUTER_API_KEY:

        print(
            "ERROR: OPENROUTER_API_KEY is missing"
        )

        return None

    title = str(
        article.get("title", "")
    ).strip()

    source = str(
        article.get("source", "")
    ).strip()

    url = str(
        article.get("url", "")
    ).strip()

    content = str(
        article.get("content", "")
    ).strip()

    if not content:
        content = title

    content = content[:18000]

    user_prompt = f"""
حلل الخبر التالي كمحرر اقتصادي سعودي.

المصدر:
{source}

العنوان:
{title}

الرابط:
{url}

محتوى الخبر:
{content}

لا تستخدم أي معلومة غير موجودة في النص أعلاه.

ركز على الاقتصاد السعودي وعلى التأثير الفعلي للخبر.

حدد:
- هل يستحق النشر؟
- درجة الأهمية من 100
- درجة الثقة
- التصنيف
- تأثيره المحتمل على السوق
- الجهات المتأثرة
- أهم المعلومات والأرقام
- سبب أهمية الخبر

أعد JSON فقط.
"""


    headers = {
        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "https://github.com/1955-wer/SaudiEconomyDaily",

        "X-OpenRouter-Title":
            "Saudi Economy Daily"
    }


    payload = {

        "model":
            MODEL,

        "messages": [

            {
                "role":
                    "system",

                "content":
                    SYSTEM_PROMPT
            },

            {
                "role":
                    "user",

                "content":
                    user_prompt
            }
        ],

        "temperature":
            0.1,

        "max_tokens":
            1200
    }


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            print(
                f"OpenRouter attempt "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = requests.post(

                API_URL,

                headers=headers,

                json=payload,

                timeout=90
            )

            print(
                f"OpenRouter status: "
                f"{response.status_code}"
            )


            if response.ok:

                data = response.json()

                choices = data.get(
                    "choices",
                    []
                )

                if not choices:

                    print(
                        "ERROR: "
                        "OpenRouter returned no choices"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                message = choices[0].get(
                    "message",
                    {}
                )

                result_text = message.get(
                    "content",
                    ""
                )


                if not result_text:

                    print(
                        "ERROR: "
                        "AI returned empty content"
                    )

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
                        "ERROR: "
                        "AI returned invalid JSON"
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
                        "ERROR: "
                        "AI result validation failed"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(3)
                        continue

                    return None


                return validated


            if response.status_code == 429:

                print(
                    "OpenRouter rate limit reached."
                )

                if attempt < MAX_RETRIES:

                    time.sleep(
                        attempt * 5
                    )

                    continue

                return None


            if response.status_code >= 500:

                print(
                    "OpenRouter server error:"
                )

                print(
                    response.text[:2000]
                )

                if attempt < MAX_RETRIES:

                    time.sleep(
                        attempt * 5
                    )

                    continue

                return None


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


        except requests.RequestException as error:

            print(
                f"OpenRouter network error: {error}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(3)

                continue

            return None


        except Exception as error:

            print(
                f"Unexpected AI error: {error}"
            )

            return None


    return None
