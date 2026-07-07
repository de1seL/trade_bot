"""
╔══════════════════════════════════════════════════════════════╗
║   📨 Sinyal Botu — Telegram bildirimcisi                      ║
║   Aynı strateji "beyni", farklı "el":                        ║
║   Borsaya EMİR GÖNDERMEZ → sana mesaj atar.                   ║
╠══════════════════════════════════════════════════════════════╣

Ne yapar:
  • trade_bot.py'deki stratejiyi AYNEN kullanır (import eder, kopyalamaz).
    → trade_bot.py'de yaptığın her iyileştirme buraya da yansır.
  • Coin tarar, sinyal üretirse Telegram'dan "AL/SAT + SL + TP" mesajı atar.
  • Aynı sinyali tekrar tekrar atmaz (her coinden tek aktif sinyal + cooldown).
  • Fiyat TP veya SL'e değince "KAPAT" mesajı atar.

Ne yapmaz:
  • Borsaya emir göndermez, para riski YOK.
  • API anahtarı GEREKMEZ (sadece halka açık piyasa verisi okur).

── KURULUM (1 kez) ───────────────────────────────────────────────
  1) Telegram'da @BotFather'a yaz → /newbot → bir bot oluştur → TOKEN al.
  2) Botuna bir "merhaba" yaz (sohbeti başlat).
  3) chat_id'ni öğren: tarayıcıda aç →
       https://api.telegram.org/bot<TOKEN>/getUpdates
     dönen JSON'da "chat":{"id": ... } senin chat_id'in.
  4) .env dosyasına ekle (trade_bot ile aynı .env):
       TELEGRAM_TOKEN=123456:ABC...
       TELEGRAM_CHAT_ID=123456789
  5) Çalıştır:  python signal_bot.py
"""

import os
import time
import json
import urllib.parse
import urllib.request
from datetime import datetime

import ccxt

# Strateji "beyni" — tek kaynak. Import etmek main()'i çalıştırmaz (o __main__ altında).
import trade_bot as tb

CONFIG = tb.CONFIG
log    = tb.log

# ─────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Sinyal botu, trade_bot ile AYNI evreni tarar (core coinler + volatil) →
# sinyaller trade_bot'un açacağı işlemlerle eşleşir. Tarama listesi ve strateji
# tamamen trade_bot'tan gelir (tek kaynak).
#
# Aynı anda kaç açık (kapanmamış) sinyal takip edilsin. Sinyal botunda
# pozisyon/marj sınırı YOK → pratikte sınırsız (coin başına zaten tek sinyal).
# Daha az bildirim istersen küçült (örn. 10).
SIGNAL_MAX_ACTIVE = 100

# Çıkış (TP/SL vurdu) mesajı da atılsın mı?
SEND_EXIT_ALERTS  = True

# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    """Telegram'a HTML mesaj gönderir. Token/chat_id yoksa sadece loglar."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("⚠️  TELEGRAM_TOKEN/CHAT_ID yok — mesaj gönderilemedi (sadece log):")
        log.info("\n" + text)
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id"   : TELEGRAM_CHAT_ID,
        "text"      : text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception as e:
            log.warning(f"⚠️  Telegram gönderim denemesi {attempt}/3 başarısız: {e}")
            time.sleep(2 * attempt)
    log.error("🚨 Telegram mesajı gönderilemedi (3 deneme).")
    return False


def fmt(x: float) -> str:
    """Fiyatı büyüklüğüne göre okunur biçimde yazar (BTC 64,000 / DOGE 0.162400)."""
    if x >= 100:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.4f}"
    return f"{x:.6f}"

# ─────────────────────────────────────────────────────────────
# BORSA (sadece OKUMA — anahtar gerektirmez)
# ─────────────────────────────────────────────────────────────

def connect_public() -> ccxt.binance:
    ex = ccxt.binance({
        "options"        : {"defaultType": "future"},
        "enableRateLimit": True,
    })
    ex.load_markets()
    log.info("✅ Binance USDT-M Futures (halka açık veri) bağlandı — emir YOK, sadece okuma")
    return ex

# ─────────────────────────────────────────────────────────────
# SİNYAL DEĞERLENDİRME (trade_bot ile birebir aynı: kapanmış mumlar)
# ─────────────────────────────────────────────────────────────

def evaluate(ex, symbol: str, btc_chg: float):
    """Bir coin için sinyal + anlık fiyat + ATR döner. trade_bot.run_symbol'ün
    sinyal kısmıyla AYNI hesabı yapar (kapanmış mum → repaint yok)."""
    price = tb.fetch_current_price(ex, symbol)
    if price is None:
        return None
    # TÜM hesabı tek try/except'e al — yeni listelenmiş / kısa geçmişli bir coin
    # indikatörü çökertse o coini ATLA, tüm botu düşürme.
    try:
        df1d = tb.fetch_ohlcv(ex, symbol, CONFIG["daily_tf"], limit=260).iloc[:-1].copy()
        df4h = tb.fetch_ohlcv(ex, symbol, CONFIG["trend_tf"], limit=250).iloc[:-1].copy()
        df1h = tb.fetch_ohlcv(ex, symbol, CONFIG["entry_tf"], limit=300).iloc[:-1].copy()

        daily = tb.calc_daily_trend(df1d)
        trend = tb.calc_trend(df4h)
        if trend is None:
            return None
        entry = tb.calc_entry(df1h)
        if entry is None:
            return None
        entry_trend = tb.calc_entry_trend(df1h)   # trade_bot'ta calc_1h_trend → calc_entry_trend

        # Alt zaman dilimi teyidi (5m + 15m) — trade_bot ile aynı
        tf5 = tf15 = "NONE"
        if CONFIG.get("ltf_confirm_enabled", True):
            try:
                df5  = tb.fetch_ohlcv(ex, symbol, "5m",  limit=120).iloc[:-1].copy()
                df15 = tb.fetch_ohlcv(ex, symbol, "15m", limit=120).iloc[:-1].copy()
                tf5  = tb.tf_trend(df5)
                tf15 = tb.tf_trend(df15)
            except Exception:
                pass

        signal      = tb.get_signal(trend, entry, daily, btc_chg, entry_trend, tf5, tf15)
        return {"price": price, "atr": entry["atr"], "signal": signal}
    except Exception as e:
        log.warning(f"⚠️  [{symbol}] değerlendirilemedi, atlanıyor: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# MESAJLAR
# ─────────────────────────────────────────────────────────────

def entry_message(symbol, side, price, sl, tp) -> str:
    coin   = symbol.split("/")[0]
    emoji  = "🟢" if side == "LONG" else "🔴"
    sl_pct = abs(price - sl) / price * 100
    tp_pct = abs(price - tp) / price * 100
    rr     = tp_pct / sl_pct if sl_pct else 0
    return (
        f"{emoji} <b>{side} SİNYALİ</b> — <b>{coin}</b>\n\n"
        f"<b>Giriş</b> : {fmt(price)}\n"
        f"<b>SL</b>    : {fmt(sl)}  (-%{sl_pct:.2f})\n"
        f"<b>TP</b>    : {fmt(tp)}  (+%{tp_pct:.2f})\n"
        f"<b>R:R</b>   : 1:{rr:.1f}   Kaldıraç: {CONFIG['leverage']}x\n\n"
        f"⏱ {datetime.now():%Y-%m-%d %H:%M}\n"
        f"<i>Not: SL/TP'yi borsaya kendin koy. Bu bir otomatik emir değildir.</i>"
    )


def exit_message(symbol, side, entry_price, exit_price, reason) -> str:
    coin    = symbol.split("/")[0]
    pnl_pct = (exit_price / entry_price - 1) * 100 if side == "LONG" \
              else (entry_price / exit_price - 1) * 100
    pnl_lev = pnl_pct * CONFIG["leverage"]
    if reason == "TP":
        head = f"✅ <b>TP VURDU — {coin}</b>  (KAPAT)"
    else:
        head = f"❌ <b>SL VURDU — {coin}</b>  (KAPAT)"
    return (
        f"{head}\n\n"
        f"Giriş : {fmt(entry_price)}\n"
        f"Çıkış : {fmt(exit_price)}\n"
        f"PnL   : %{pnl_pct:+.2f}  (kaldıraçlı %{pnl_lev:+.2f})\n"
        f"⏱ {datetime.now():%Y-%m-%d %H:%M}"
    )

# ─────────────────────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("⚠️  TELEGRAM_TOKEN / TELEGRAM_CHAT_ID .env'de yok — mesajlar sadece konsola yazılacak.")

    ex = connect_public()

    symbols = tb.build_scan_list(ex)   # core + volatil (trade_bot ile aynı)
    last_refresh = time.time()

    active    = {}   # symbol -> {"side","entry","sl","tp","time"} (takip edilen açık sinyal)
    cooldown  = {}   # symbol -> cooldown bitiş zamanı (ts)

    log.info("=" * 54)
    log.info("  📨 Sinyal Botu (Telegram)")
    _cap = "sınırsız (iyi sinyal varsa hepsi)" if SIGNAL_MAX_ACTIVE >= len(symbols) else f"max {SIGNAL_MAX_ACTIVE}"
    _mode = "sabit liste" if CONFIG["symbols"] else f"{len(CONFIG.get('core_symbols', []))} core + volatil"
    log.info(f"  Coinler        : {len(symbols)} taranıyor ({_mode}) — trade_bot ile aynı")
    log.info(f"  Sinyal limiti   : {_cap}")
    log.info(f"  Çıkış uyarısı   : {'açık' if SEND_EXIT_ALERTS else 'kapalı'}")
    log.info("=" * 54)
    send_message(
        f"📨 <b>Sinyal botu başladı</b>\n"
        f"{len(symbols)} coin taranıyor — iyi sinyal veren her coin için mesaj gelecek.\n"
        f"⏱ {datetime.now():%Y-%m-%d %H:%M}"
    )

    while True:
        # Dinamik sembol yenileme (açık sinyalli coinleri düşürmeden — trade_bot ile aynı mantık)
        if not CONFIG["symbols"] and time.time() - last_refresh > CONFIG["symbol_refresh_sec"]:
            log.info("🔄 Volatil coinler yenileniyor (core sabit)...")
            new_syms = tb.build_scan_list(ex)
            held     = [s for s in active if s not in new_syms]
            symbols      = list(dict.fromkeys(new_syms + held))
            last_refresh = time.time()

        btc_chg = tb.get_btc_change(ex)

        for sym in symbols:
            ev = evaluate(ex, sym, btc_chg)
            if ev is None:
                time.sleep(0.3)
                continue
            price = ev["price"]

            # ── 1. Açık sinyal varsa TP/SL kontrolü ──
            if sym in active:
                s = active[sym]
                hit = None
                if s["side"] == "LONG":
                    if price >= s["tp"]:   hit = "TP"
                    elif price <= s["sl"]: hit = "SL"
                else:
                    if price <= s["tp"]:   hit = "TP"
                    elif price >= s["sl"]: hit = "SL"
                if hit:
                    if SEND_EXIT_ALERTS:
                        send_message(exit_message(sym, s["side"], s["entry"], price, hit))
                    log.info(f"{'✅' if hit=='TP' else '❌'} [{sym}] {hit} vurdu @ {fmt(price)} — sinyal kapandı")
                    cd = CONFIG["cooldown_tp_sec"] if hit == "TP" else CONFIG["cooldown_sl_sec"]
                    cooldown[sym] = time.time() + cd
                    del active[sym]
                time.sleep(0.3)
                continue

            # ── 2. Cooldown'daysa atla ──
            if cooldown.get(sym, 0) > time.time():
                time.sleep(0.3)
                continue

            # ── 3. Yeni sinyal ──
            if ev["signal"] in ("LONG", "SHORT") and len(active) < SIGNAL_MAX_ACTIVE:
                side   = ev["signal"]
                sl, tp = tb.compute_sltp(price, ev["atr"], side)
                active[sym] = {"side": side, "entry": price, "sl": sl, "tp": tp, "time": time.time()}
                send_message(entry_message(sym, side, price, sl, tp))
                log.info(f"📨 [{sym}] {side} sinyali gönderildi  giriş={fmt(price)} SL={fmt(sl)} TP={fmt(tp)}")

            time.sleep(0.3)

        log.info(f"⏳ {CONFIG['loop_sec']}s bekleniyor...  [Aktif sinyal: {len(active)}/{SIGNAL_MAX_ACTIVE}]\n")
        time.sleep(CONFIG["loop_sec"])


if __name__ == "__main__":
    main()
