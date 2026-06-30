"""
🔎 chat_id bulucu — Telegram grup/kişi id'sini KESİN öğrenmek için.

Kullanım:
  1) .env'de TELEGRAM_TOKEN dolu olsun (signal_bot ile aynı .env).
  2) Botu gruba ekle.
  3) GRUPTA şunu yaz:   /id@senin_bot_kullanici_adin
     (Komut '/' ile başladığı için bot bunu privacy ayarı KAPALI olsa bile görür.)
  4) Bu scripti çalıştır:   python get_chat_id.py
  5) Çıktıdaki grubun 'id' değerini (eksi işaretiyle) .env'deki TELEGRAM_CHAT_ID'ye yaz.
"""

import os
import json
import urllib.request

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()


def main():
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN .env'de yok. Önce token'ı ekle.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
    except Exception as e:
        print(f"❌ Telegram'a ulaşılamadı (token yanlış olabilir): {e}")
        return

    if not data.get("ok"):
        print(f"❌ Telegram hatası: {data}")
        return

    updates = data.get("result", [])
    if not updates:
        print("⚠️  Hiç güncelleme yok. Şunları yap:")
        print("   • Kişisel için: kendi botuna özelden bir mesaj yaz.")
        print("   • Grup için   : botu gruba ekle, GRUPTA  /id@bot_kullanici_adin  yaz.")
        print("   Sonra bu scripti tekrar çalıştır.")
        return

    # Görülen tüm farklı sohbetleri topla
    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            seen[chat["id"]] = chat

    print("\n✅ Botun gördüğü sohbetler:\n" + "─" * 50)
    for cid, chat in seen.items():
        ctype = chat.get("type", "?")
        name  = chat.get("title") or chat.get("first_name") or chat.get("username") or ""
        etiket = "👥 GRUP" if ctype in ("group", "supergroup") else "👤 KİŞİ"
        print(f"  {etiket}  →  chat_id = {cid}")
        print(f"            tür: {ctype}   ad: {name}")
        print("─" * 50)
    print("\n📌 .env'e şöyle yaz (gruplar EKSİ işaretlidir):")
    print("   TELEGRAM_CHAT_ID=<yukarıdaki chat_id>\n")


if __name__ == "__main__":
    main()
