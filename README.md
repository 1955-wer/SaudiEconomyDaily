# 🇸🇦 Saudi Economy Daily

نظام لجمع الأخبار الاقتصادية السعودية وإرسال نشرة Telegram، مع طبقة **Hermes Deep Research** اختيارية تقوم بالبحث الخارجي والتحقق وربط السياق قبل صياغة الخبر النهائي.

## البنية الحالية بعد الدمج

```text
مصادر الأخبار
    ↓
SaudiEconomyDaily
    ├─ RSS / Google News / Website
    ├─ فلترة أولية
    ├─ إزالة التكرار
    └─ استخراج محتوى الصفحة
    ↓
Hermes Research Layer
    ├─ بحث ويب متعدد الخطوات
    ├─ مقارنة مصادر مستقلة
    ├─ البحث عن المصدر الرسمي عند الإمكان
    ├─ ربط الأخبار والأحداث السابقة
    ├─ كشف القصص المكررة
    └─ إعداد خبر واحد غني بالمعلومات
    ↓
Formatter
    ↓
Telegram
```

Hermes **لا يرسل منشورًا ثانيًا**. هو طبقة بحث فوق المرشح نفسه، ثم يمر الناتج إلى نفس Formatter ونفس Telegram الموجودين في المشروع.

## النموذج الافتراضي

```text
inclusionai/ling-3.0-flash-fin:free
```

المشروع لا يثبت النموذج نفسه؛ Hermes يستخدم OpenRouter عبر `OPENROUTER_API_KEY`.

## المتطلبات

- Python 3.12
- مفاتيح GitHub Actions التالية:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `OPENROUTER_API_KEY`
- تثبيت Hermes في بيئة التشغيل. الـworkflow يحاول تثبيته تلقائيًا، وإذا فشل التثبيت يعود البرنامج إلى النظام القديم بدلاً من إيقاف النشرة.

### البحث على الويب

Hermes يستطيع استخدام `web_search`. افتراضيًا يترك المشروع اختيار backend للتكوين التلقائي لدى Hermes. ويمكنك فرض backend عبر متغير GitHub Repository Variable:

```text
HERMES_WEB_BACKEND=ddgs
```

`ddgs` مجاني ولا يحتاج مفتاحًا، لكنه بحث فقط. عند استخدام backend يدعم الاستخراج يمكن لـHermes أيضًا قراءة الصفحة مباشرة. يمكنك لاحقًا ضبط backend مدعوم آخر بدون تغيير كود المشروع.

## التشغيل والرجوع

الوضع الافتراضي في `config/hermes.json` هو Hermes:

```json
{
  "enabled": true,
  "fallback_to_legacy": true
}
```

### تشغيل Hermes

لا تحتاج إلى إضافة متغير إذا أبقيت الإعداد الافتراضي:

```text
NEWS_PROCESSOR=hermes
```

### العودة للنظام السابق

ضع GitHub Repository Variable باسم:

```text
NEWS_PROCESSOR=legacy
```

فيصبح المسار:

```text
SaudiEconomyDaily → ai_editor.py → Telegram
```

بدلاً من:

```text
SaudiEconomyDaily → Hermes → Telegram
```

### Fallback تلقائي

حتى في وضع Hermes، إذا فشل أي من الآتي:

- لم يتم العثور على أمر `hermes`.
- فشل Hermes في التنفيذ.
- انتهت مهلة البحث.
- أعاد Hermes JSON غير صالح.
- تعذر الوصول إلى OpenRouter.

فإن البرنامج يحاول تشغيل `ai_editor.py` القديم، ما لم تعطل ذلك صراحة عبر:

```text
HERMES_FALLBACK_TO_LEGACY=0
```

وهكذا لا يصبح Hermes نقطة فشل وحيدة للنشرة.

## إعدادات Hermes

الملف:

```text
config/hermes.json
```

الإعدادات:

```json
{
  "enabled": true,
  "fallback_to_legacy": true,
  "model": "inclusionai/ling-3.0-flash-fin:free",
  "max_turns": 8,
  "timeout_seconds": 420,
  "max_candidates": 3,
  "web_backend": ""
}
```

### وظيفة الإعدادات

- `enabled`: تفعيل/تعطيل طبقة Hermes.
- `fallback_to_legacy`: الرجوع تلقائيًا إلى النظام الحالي عند الفشل.
- `model`: نموذج OpenRouter المستخدم بواسطة Hermes.
- `max_turns`: الحد الأقصى لخطوات agent في الجلسة الواحدة.
- `timeout_seconds`: حد زمني للبحث.
- `max_candidates`: عدد المرشحين الذين يدخلون البحث العميق في كل تشغيل.
- `web_backend`: اتركه فارغًا للاكتشاف التلقائي، أو ضع backend صريحًا مثل `ddgs`.

يمكن تجاوز هذه القيم عبر متغيرات البيئة:

```text
HERMES_MODEL
HERMES_MAX_TURNS
HERMES_TIMEOUT_SECONDS
HERMES_MAX_CANDIDATES
HERMES_WEB_BACKEND
HERMES_FALLBACK_TO_LEGACY
HERMES_BINARY
```

## منطق البحث

Hermes يستلم الأخبار التي اجتازت الفلترة الأولية في `fetch_news.py`. لا يتم إرسال كل الأخبار التي يجدها النظام للمحرك العميق؛ يتم اختيار أعلى المرشحين بحسب حداثة الخبر، أولوية المصدر، الكلمات الاقتصادية، ونوع المحتوى.

كل تشغيل يرسل مجموعة صغيرة من المرشحين إلى **جلسة Hermes واحدة**. هذا يسمح للمحرك برؤية القصص معًا وربط الأحداث المرتبطة، مع إبقاء كل قصة منشورة كعنصر مستقل إذا كانت حدثًا مختلفًا.

Hermes يطلب لكل قصة:

1. البحث في الويب عن نفس الخبر.
2. مقارنة مصادر مستقلة.
3. البحث عن مصدر رسمي أو أولي عندما يكون ذلك ممكنًا.
4. ربط التطورات السابقة والجارية بالقصة.
5. التمييز بين الحقائق المؤكدة والادعاءات والتحليل.
6. تحديد ما إذا كان مرشح آخر يكرر نفس الحدث.
7. إنتاج JSON منظم يمر عبر طبقة تحقق قبل Telegram.

## مبدأ عدم اختلاق المعلومات

Hermes مطالب صراحةً بعدم اختراع رقم أو تاريخ أو مصدر أو رابط. الكود لا يقبل مصدرًا مساندًا ما لم يكن رابطًا HTTP/HTTPS صحيح الصياغة، ولا يسمح بنشر نتيجة ناقصة العنوان أو الملخص.

لا يتم فرض JSON Schema من OpenRouter؛ لذلك هناك parser وnormalizer محليان قبل النشر.

## صيغة الخبر النهائية

لكل قصة منشورة يكون الشكل قريبًا من:

```text
📰 العنوان

الملخص الغني بالمعلومات...

📌 أبرز المعلومات:
• ...
• ...
• ...

🏢 الجهات المتأثرة:
...

💡 لماذا يهم؟
...

📊 القطاع: الأسواق
📈 التأثير المحتمل: سلبي
🔴 الأهمية: 80/100
🎯 الثقة: 90/100

🔎 مصادر مساندة: Reuters · SPA

📰 المصدر:
أرقام

🔗 رابط الخبر:
https://...
```

المصدر الأصلي يبقى ظاهرًا في خانة `📰 المصدر`، بينما المصادر التي استخدمها Hermes للتحقق تظهر بشكل منفصل عند توفرها.

## GitHub Actions

الملف الرئيسي:

```text
.github/workflows/test-news.yml
```

التنفيذ المجدول يبقى في أوقات المشروع الحالية. قبل تشغيل Python يحاول الـworkflow تثبيت Hermes باستخدام المثبت الرسمي، مع عدم فشل المهمة إذا تعذر التثبيت. هذه النقطة مقصودة لحماية المسار القديم.

بعد ذلك يتم تشغيل:

```bash
python src/fetch_news.py
```

## الاختبار المحلي

بدون Hermes يمكنك دائمًا اختبار النظام القديم:

```bash
NEWS_PROCESSOR=legacy python src/fetch_news.py
```

ولتشغيل Hermes محليًا، يجب أن يكون الأمر `hermes` متاحًا في `PATH` وأن يكون `OPENROUTER_API_KEY` موجودًا في البيئة.

## ملفات الدمج الجديدة

```text
src/hermes_researcher.py   # تشغيل Hermes، البحث، parsing والتحقق
config/hermes.json         # إعدادات طبقة البحث
.gitignore                 # منع حفظ ملفات Hermes المؤقتة
```

تم تعديل `src/fetch_news.py` ليوجه الخبر إلى Hermes أو إلى `ai_editor.py` القديم، مع fallback تلقائي، كما تم تحسين Escape لمحتوى Telegram وتوسيع أبرز المعلومات إلى 4 نقاط عند توفرها. وإذا تجاوزت النشرة حد Telegram، يتم تقسيمها عند فواصل آمنة بدل إسقاط الإرسال.
