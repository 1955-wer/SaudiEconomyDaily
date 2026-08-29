import os
import requests
import feedparser

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

print("Starting news test")

feed = feedparser.parse("https://feeds.bbci.co.uk/arabic/rss.xml")

print("RSS entries: " + str(len(feed.entries)))

entry = feed.entries[0]

title = entry.get("title", "خبر")
url = entry.get("link", "")

message = "🇸🇦 <b>Saudi Economy Daily</b>\n\n📰 <b>" + title + "</b>\n\n📌 المصدر: BBC Arabic\n🔗 " + url

telegram_url = "https://api.telegram.org/bot" + token + "/sendMessage"

response = requests.post(telegram_url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=20)

print("Telegram status: " + str(response.status_code))

print(response.text)
