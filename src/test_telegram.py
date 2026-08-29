import os
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

message = """🤖 اختبار نظام النشرة الاقتصادية السعودية

✅ تم الاتصال بـ Telegram بنجاح.
✅ GitHub Actions جاهز.
🇸🇦 القناة جاهزة لاستقبال الأخبار.

الخطوة القادمة:
📰 جمع الأخبار
🔎 فلترة الأخبار الاقتصادية السعودية
🧠 التلخيص
📢 النشر التلقائي
"""

response = requests.post(
    url,
    json={
        "chat_id": CHAT_ID,
        "text": message
    },
    timeout=30
)

response.raise_for_status()

data = response.json()

if not data.get("ok"):
    raise RuntimeError(data)

print("Telegram message sent successfully.")
