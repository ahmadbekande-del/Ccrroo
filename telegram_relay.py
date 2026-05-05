"""
📡 Telegram Relay — وسيط الإرسال
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يعمل على أي جهاز أو Replit مجاناً
يسحب الرسائل من Hugging Face ويرسلها لتيليغرام

التشغيل:
  pip install requests
  python telegram_relay.py
"""

import requests, time, os

# ─── إعداداتك ──────────────────────────────────────────────
HF_URL   = "https://YOUR_NAME-destroyer-v5.hf.space"  # رابط HF Space
TG_TOKEN = os.getenv("TG_TOKEN", "ضع_التوكن_هنا")
TG_CHAT  = os.getenv("TG_CHAT",  "ضع_الشات_آيدي_هنا")
INTERVAL = 30   # فحص كل 30 ثانية
# ───────────────────────────────────────────────────────────


def send_tg(text):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        r = requests.post(url, json={
            'chat_id'   : TG_CHAT,
            'text'      : text,
            'parse_mode': 'Markdown'
        }, timeout=15)
        return r.json().get('ok', False)
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def pull_and_send():
    try:
        r = requests.get(f"{HF_URL}/api/messages", timeout=20)
        data = r.json()
        msgs = data.get('messages', [])
        if not msgs:
            return 0
        sent = 0
        for msg in msgs:
            ok = send_tg(msg['text'])
            if ok:
                sent += 1
                print(f"✅ أُرسلت: {msg['text'][:50]}...")
            else:
                print(f"❌ فشل الإرسال")
            time.sleep(1)
        return sent
    except Exception as e:
        print(f"⚠️ خطأ في السحب: {e}")
        return 0


def main():
    print("━" * 50)
    print("📡 Telegram Relay — يعمل الآن")
    print(f"   HF URL : {HF_URL}")
    print(f"   فحص كل: {INTERVAL} ثانية")
    print("━" * 50)

    # اختبار تيليغرام
    if send_tg("✅ *Relay يعمل!*\nسيبدأ استقبال الإشارات الآن 🚀"):
        print("✅ تيليغرام متصل")
    else:
        print("❌ تحقق من TG_TOKEN و TG_CHAT")
        return

    total_sent = 0
    while True:
        count = pull_and_send()
        if count > 0:
            total_sent += count
            print(f"📊 الإجمالي المُرسل: {total_sent} رسالة")
        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
