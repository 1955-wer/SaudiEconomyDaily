import os
import json
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "inclusionai/ling-3.0-flash-fin:free"


SYSTEM_PROMPT = """
أنت محرر اقتصادي محترف متخصص في الاقتصاد السعودي.

مهمتك قراءة الخبر الذي سيتم إرساله لك وتحديد هل يستحق النشر في قناة
Saudi Economy Daily أم لا.

ركز على الأخبار التي لها تأثير أو أهمية حقيقية على:

- الاقتصاد السعودي
- النفط والطاقة
- أرامكو
- البنوك والقطاع المالي
- سوق الأسهم السعودي
- الشركات السعودية الكبرى
- الاستثمار
- المشاريع الكبرى ورؤية 2030
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

مهم جداً:
- لا تخترع أي معلومة.
- لا تخترع أرقاماً.
- لا تغير الأرقام الموجودة في الخبر.
- لا تضف معلومات غير موجودة في النص.
- إذا كانت معلومة غير موجودة، لا تذكرها.
- لا تعتمد على معرفتك السابقة لتأكيد معلومات غير موجودة في الخبر.
- إذا كان الخبر غير واضح أو لا يحتوي على معلومات كافية، اجعل publish=false.

أعطِ درجة أهمية من 0 إلى 100.

التصنيف:
0-49 = غير مهم
50-69 = منخفض
70-84 = مهم
85-94 = مهم جداً
95-100 = عاجل / شديد الأهمية

يجب أن تكون الإجابة JSON فقط بدون Markdown وبدون ```.

الصيغة المطلوبة:

{
  "publish": true,
  "importance": 85,
  "category": "oil",
  "headline": "عنوان عربي مختصر",
  "summary": "ملخص الخبر في 2 إلى 3 جمل",
  "why_it_matters": "لماذا هذا الخبر مهم للاقتصاد السعودي؟",
  "key_facts": [
    "معلومة مهمة من الخبر"
  ]
}

إذا كان الخبر غير مهم:

{
  "publish": false,
  "importance": 30,
  "category": "other",
  "headline": "",
  "summary": "",
  "why_it_matters": "",
  "key_facts": []
}
"""


def analyze_article(article):
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY is missing")
        return None

    title = article.get("title", "")
    source = article.get("source", "")
    url = article.get("url", "")
    content = article.get("content", "")

    if not content:
        content = title

    # حماية من إرسال نص ضخم جدًا في الاختبار
    content = content[:15000]

    user_prompt = f"""
حلل الخبر التالي:

المصدر:
{source}

العنوان:
{title}

الرابط:
{url}

محتوى الخبر:
{content}
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/1955-wer/SaudiEconomyDaily",
        "X-Title": "Saudi Economy Daily"
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
        "temperature": 0.2,
        "max_tokens": 700
    }

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=60
        )

        print(f"OpenRouter status: {response.status_code}")

        if not response.ok:
            print(response.text)
            return None

        data = response.json()

        result_text = data["choices"][0]["message"]["content"].strip()

        # إزالة Markdown إذا النموذج أضافه رغم التعليمات
        if result_text.startswith("```"):
            result_text = result_text.replace("```json", "")
            result_text = result_text.replace("```", "")
            result_text = result_text.strip()

        result = json.loads(result_text)

        return result

    except json.JSONDecodeError:
        print("ERROR: AI returned invalid JSON")
        print(result_text if "result_text" in locals() else "")
        return None

    except Exception as e:
        print(f"OpenRouter ERROR: {e}")
        return None

