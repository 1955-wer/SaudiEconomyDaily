import json
import os
import sys

from hermes_researcher import research_articles


def main():
    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY is missing")
        return 2

    article = {
        "id": "smoke-test-001",
        "title": "اختبار بحث عميق عن الاقتصاد السعودي",
        "source": "اختبار داخلي",
        "source_type": "test",
        "url": "https://www.spa.gov.sa/",
        "published_at": "",
        "content": "اختبار تقني فقط. ابحث عن أحدث تطورات اقتصادية مرتبطة بالسعودية، وتحقق من مصدر رسمي ومصدر مستقل إن أمكن.",
    }

    results = research_articles(
        [article],
        [
            {
                "name": "وكالة الأنباء السعودية (واس)",
                "url": "https://www.spa.gov.sa/",
                "type": "official",
                "topics": ["saudi_economy", "government", "energy"],
            }
        ],
    )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
