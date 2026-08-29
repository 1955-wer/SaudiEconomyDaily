import os
import requests
import feedparser

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

print("Starting Saudi Economy Daily")

rss_url = "https://feeds.bbci.co.uk/arabic/rss.xml"

print("Reading RSS...")
feed = feedparser.parse(rss_url)

print("Articles found: " + str(len(feed.entries)))

if len(feed.entries) == 0:
print("No articles found")
raise SystemExit(0)

entry = feed.entries[0]

title = entry.get("title", "خبر اقتصادي")
url = entry.get("link", "")

message = (
"🇸🇦 <b>Saudi Economy Daily</b>\n\n"
"📰 <b>" + title + "</b>\n\n"
"📌 المصدر: BBC Arabic\n"
"🔗 " + url
)

print("Sending article to Telegram...")

telegram_url = "https://api.telegram.org/bot" + token + "/sendMessage"

response = requests.post(
telegram_url,
json={
"chat_id": chat_id,
"text": message,
"parse_mode": "HTML"
},
timeout=20
)

print("Telegram status: " + str(response.status_code))
print(response.text)

if response.status_code == 200:
print("SUCCESS: Article sent to Telegram")
else:
print("ERROR: Telegram failed")
