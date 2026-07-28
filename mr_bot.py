"""
╔══════════════════════════════════════════════════════════════╗
║  mr_bot.py — MEAN-REVERSION FORWARD TEST (DRY-RUN)            ║
╠══════════════════════════════════════════════════════════════╣
Amaç: OOS backtest'te PF ~1.27 / WR %64 veren mean-reversion stratejisini
CANLI FİYATLARLA, GERÇEK EMİR AÇMADAN (dry-run) ileriye dönük test etmek.
Sinyalleri ve kağıt-üstü sonuçları Telegram'a yollar + mr_trades.csv'ye yazar.

Donmuş strateji (OOS doğrulandı — DEĞİŞTİRME):
  LONG : close>EMA200(1h)  VE  RSI(2)<5  VE  close < Bollinger alt-band
  SHORT: close<EMA200(1h)  VE  RSI(2)>95 VE  close > Bollinger üst-band
  ÇIKIŞ: RSI(2)>65 (long) / <35 (short)  |  felaket-stop: 3.0×ATR  |  max 24s
  Kaldıraç 5x (kağıt), pozisyon başı sabit trade_usdt (kağıt).

Mevcut trade_bot.py'nin ALTYAPISINI kullanır (notify, exchange, fetch, coin seçimi)
ama ONA DOKUNMAZ. GERÇEK PARA YOK — sadece forward doğrulama.

Çalıştırma:  python mr_bot.py     (durdurmak: Ctrl+C)
"""
import os, json, time
from datetime import datetime, timezone

import numpy as np
import trade_bot as tb

log = tb.log
tb.CONFIG["dry_run"] = True                 # gerçek emir YOK, private çağrı YOK
# Coin havuzunu genişlet: get_symbols "24s'te ≥%3 oynayan" filtresini kullanıyor →
# sakin günde ~40 coin geçiyor. 3.0→1.5 ile daha çok coin havuza girer (~70-80).
# Hacim ≥$10M filtresi DURUYOR (likidite mean-reversion için önemli).
tb.CONFIG["min_volatility_pct"] = 1.5

# ── Ayarlar ──
# RSI<5: OOS'ta volatil evrende RSI<3'ten DAHA İYİ (PF 1.39 vs 1.26, %33 daha çok
# işlem, aynı WR). Sadece volatilde geçerli (likitte çöküyor); mr_bot zaten volatil
# tarıyor. rsi_sell = 100 - rsi_buy = 95.
FROZEN = dict(rsi_buy=5, rsi_sell=95, rsi_exit_l=65, rsi_exit_s=35,
              ema=200, bb_len=20, bb_mult=2.0, atr_stop=3.0, max_hold_h=24)
LEV            = 5
TRADE_USDT     = 10          # kağıt pozisyon büyüklüğü (marj)
MAX_POSITIONS  = 8           # daha çok eşzamanlı poz = daha çok çeşitlendirme = düşük varyans
TOP_N          = 80          # daha çok coin = daha çok işlem, AYNI edge (eşiği gevşetmeden)
LOOP_SEC       = 60          # 1 dk — strateji 1h mumlu, bundan hızlısı fayda vermez (rate-limit + repaint riski)
REFRESH_SEC    = 900         # coin listesini 15 dk'da bir yenile
STATUS_SEC     = 3600         # Telegram'a periyodik özet (WR/PnL) — saatte bir
MIN_HIST       = 260
STATE_FILE     = "mr_positions.json"
TRADES_CSV     = "mr_trades.csv"
LOCK_FILE      = "mr_bot.lock"
COST_FR        = tb.CONFIG["commission"] + tb.CONFIG["slippage"]


def _lock_alive():
    """Başka bir mr_bot canlı mı? (lock dosyası son 3 döngüde güncellenmişse evet)"""
    if not os.path.isfile(LOCK_FILE):
        return False
    try:
        return (time.time() - os.path.getmtime(LOCK_FILE)) < LOOP_SEC * 3
    except Exception:
        return False


def _touch_lock():
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def now_utc():
    return datetime.now(timezone.utc)


def load_state():
    if os.path.isfile(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            return {}
    return {}


def save_state(pos):
    try:
        json.dump(pos, open(STATE_FILE, "w"), indent=2)
    except Exception as e:
        log.warning(f"⚠️  state yazılamadı: {e}")


def log_trade(row):
    import csv
    exists = os.path.isfile(TRADES_CSV)
    with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time", "symbol", "side", "entry", "exit",
                                          "pnl_pct", "pnl_usdt", "reason", "dur_min"])
        if not exists:
            w.writeheader()
        w.writerow(row)


def compute_stats():
    """mr_trades.csv'den kümülatif özet: n, W/L, WR, PnL$, PF (restart'ta da doğru)."""
    import csv
    if not os.path.isfile(TRADES_CSV):
        return None
    n = w = 0; usd = 0.0; gw = gl = 0.0
    try:
        with open(TRADES_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                p = float(r["pnl_usdt"])
                n += 1; usd += p
                if p > 0: w += 1; gw += p
                else: gl += -p
    except Exception:
        return None
    if n == 0:
        return None
    return {"n": n, "w": w, "l": n - w, "wr": w / n * 100, "usd": usd,
            "pf": (gw / gl if gl > 0 else 99)}


def stats_line():
    s = compute_stats()
    if not s:
        return "📊 Henüz kapanan işlem yok"
    return (f"📊 Toplam {s['n']} işlem: {s['w']}W/{s['l']}L (%{s['wr']:.0f} WR)  •  "
            f"PnL {s['usd']:+.2f}$ kağıt  •  PF {s['pf']:.2f}")


def indicators(df):
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, 2).rsi()
    ema  = tb.ta.trend.EMAIndicator(c, FROZEN["ema"]).ema_indicator()
    atr  = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    bb   = tb.ta.volatility.BollingerBands(c, FROZEN["bb_len"], FROZEN["bb_mult"])
    return rsi2, ema, atr, bb.bollinger_lband(), bb.bollinger_hband(), bb.bollinger_mavg()


def check_entry(df):
    """Son kapalı mumda giriş sinyali? → (side, entry, sl, hedef) veya None.
    hedef = orta bant (20-ort) — gösterge; gerçek çıkış RSI toparlamasıyla (dinamik)."""
    rsi2, ema, atr, lo_bb, up_bb, mid = indicators(df)
    i = len(df) - 1
    r = rsi2.iloc[i]; e = ema.iloc[i]; c = float(df["close"].iloc[i]); av = atr.iloc[i]
    if any(np.isnan(x) for x in (r, e, av, lo_bb.iloc[i], up_bb.iloc[i], mid.iloc[i])):
        return None
    tgt = float(mid.iloc[i])
    if c > e and r < FROZEN["rsi_buy"] and c < lo_bb.iloc[i]:
        return "LONG", c, c - FROZEN["atr_stop"] * av, tgt
    if c < e and r > FROZEN["rsi_sell"] and c > up_bb.iloc[i]:
        return "SHORT", c, c + FROZEN["atr_stop"] * av, tgt
    return None


def check_exit(df, p):
    """Açık pozisyon kapanmalı mı? → (reason, exit_price) veya None."""
    rsi2, ema, atr, lo_bb, up_bb, mid = indicators(df)
    i = len(df) - 1
    r = rsi2.iloc[i]
    hi = float(df["high"].iloc[i]); lo = float(df["low"].iloc[i]); c = float(df["close"].iloc[i])
    side = p["side"]; sl = p["sl"]
    # felaket-stop
    if side == "LONG" and lo <= sl:
        return "STOP", sl
    if side == "SHORT" and hi >= sl:
        return "STOP", sl
    # RSI reversion çıkışı
    if side == "LONG" and not np.isnan(r) and r > FROZEN["rsi_exit_l"]:
        return "RSI_EXIT", c
    if side == "SHORT" and not np.isnan(r) and r < FROZEN["rsi_exit_s"]:
        return "RSI_EXIT", c
    # zaman limiti
    opened = datetime.fromisoformat(p["opened"])
    if (now_utc() - opened).total_seconds() / 3600 >= FROZEN["max_hold_h"]:
        return "TIME", c
    return None


def pnl_pct(side, entry, exit_px):
    raw = (exit_px/entry - 1) * 100 * LEV if side == "LONG" else (entry/exit_px - 1) * 100 * LEV
    return raw - COST_FR * 2 * 100 * LEV


def main():
    if _lock_alive():
        log.error("⛔ Başka bir mr_bot ZATEN çalışıyor (mr_bot.lock taze). "
                  "İki kopya aynı anda çalıştırma — istatistiği bozar, riski 2'ye katlar.")
        log.error("   Gerçekten tek kopya kaldıysa mr_bot.lock dosyasını sil ve tekrar başlat.")
        return
    _touch_lock()
    log.info("🟣 MEAN-REVERSION DRY-RUN başlıyor (RSI<5+BB+200EMA, 5x kağıt)")
    log.info(f"   max {MAX_POSITIONS} poz, {TRADE_USDT}$/poz (kağıt), tarama {TOP_N} coin")
    notify_ok = tb.CONFIG.get("notify_telegram") and tb.TELEGRAM_TOKEN and tb.TELEGRAM_CHAT_ID
    tb.notify("🟣 <b>Mean-Reversion DRY-RUN başladı</b>\n"
              "RSI(2)&lt;5 + Bollinger + 200EMA | 5x kağıt | gerçek emir YOK\n"
              "Sinyaller ve kağıt sonuçlar buraya düşecek.")
    if not notify_ok:
        log.warning("⚠️  Telegram kapalı/token yok — mesajlar sadece log'a. (.env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)")

    ex = tb.connect_exchange()
    positions = load_state()
    symbols = []
    last_refresh = 0.0
    last_status = time.time()

    while True:
        try:
            # coin listesini periyodik yenile
            if time.time() - last_refresh > REFRESH_SEC or not symbols:
                try:
                    symbols = tb.get_symbols(ex, TOP_N)
                except Exception as e:
                    log.warning(f"⚠️  coin taraması hatası: {e}")
                    symbols = symbols or tb.FALLBACK
                last_refresh = time.time()

            # 1) açık pozisyonları yönet (çıkış kontrolü)
            for sym in list(positions.keys()):
                p = positions[sym]
                try:
                    df = tb.fetch_ohlcv(ex, sym, "1h", limit=MIN_HIST + 20)
                except Exception as e:
                    log.warning(f"⚠️  {sym} veri hatası: {e}"); continue
                ex_res = check_exit(df, p)
                if ex_res:
                    reason, exit_px = ex_res
                    pct = pnl_pct(p["side"], p["entry"], exit_px)
                    usdt = TRADE_USDT * pct / 100
                    dur = (now_utc() - datetime.fromisoformat(p["opened"])).total_seconds() / 60
                    emoji = "✅" if pct > 0 else "❌"
                    log.info(f"{emoji} [DRY] {sym} {p['side']} KAPAT {pct:+.2f}% ({reason})")
                    log_trade({"time": now_utc().strftime("%Y-%m-%d %H:%M:%S"),
                               "symbol": sym.split("/")[0], "side": p["side"],
                               "entry": p["entry"], "exit": round(exit_px, 8),
                               "pnl_pct": round(pct, 2), "pnl_usdt": round(usdt, 2),
                               "reason": reason, "dur_min": round(dur)})
                    del positions[sym]
                    save_state(positions)
                    tb.notify(f"{emoji} <b>[DRY] {sym.split('/')[0]} KAPAT</b>  {p['side']}\n"
                              f"giriş {p['entry']:.6g} → çıkış {exit_px:.6g}\n"
                              f"PnL: <b>{pct:+.2f}%</b> ({usdt:+.2f}$ kağıt)  •  {reason}  •  {dur:.0f}dk\n"
                              f"{stats_line()}")

            # 2) yeni giriş ara (boş slot varsa)
            if len(positions) < MAX_POSITIONS:
                for sym in symbols:
                    if len(positions) >= MAX_POSITIONS:
                        break
                    if sym in positions:
                        continue
                    try:
                        df = tb.fetch_ohlcv(ex, sym, "1h", limit=MIN_HIST + 20)
                    except Exception:
                        continue
                    if len(df) < MIN_HIST:
                        continue
                    sig = check_entry(df)
                    if sig:
                        side, entry, sl, tgt = sig
                        positions[sym] = {"side": side, "entry": entry, "sl": sl,
                                          "target": tgt, "opened": now_utc().isoformat()}
                        save_state(positions)
                        arrow = "🟢 AL" if side == "LONG" else "🔴 SAT"
                        tb.notify(f"{arrow} <b>[DRY] {sym.split('/')[0]}</b>  {side}\n"
                                  f"giriş {entry:.6g}  •  stop {sl:.6g}\n"
                                  f"≈hedef {tgt:.6g} (orta bant)  •  çıkış: RSI toparlayınca (dinamik)\n"
                                  f"sebep: RSI(2) aşırı {'dip' if side=='LONG' else 'tepe'} + Bollinger + trend")
                        log.info(f"{arrow} [DRY] {sym} {side} giriş {entry:.6g} stop {sl:.6g} ≈hedef {tgt:.6g}")

            _touch_lock()                         # canlıyım heartbeat (ikinci kopyayı engeller)
            open_c = len(positions)
            log.info(f"⏳ {LOOP_SEC}s bekleniyor... [açık: {open_c}/{MAX_POSITIONS}]  {stats_line()}")
            # saatte bir Telegram özeti (throttle)
            if time.time() - last_status > STATUS_SEC:
                tb.notify(f"🟣 <b>Durum</b> — açık kağıt poz: {open_c}/{MAX_POSITIONS}\n{stats_line()}")
                last_status = time.time()
            time.sleep(LOOP_SEC)

        except KeyboardInterrupt:
            log.info("👋 Dry-run kullanıcı tarafından durduruldu.")
            tb.notify("🟣 Mean-Reversion DRY-RUN durduruldu.")
            try: os.remove(LOCK_FILE)
            except Exception: pass
            break
        except Exception as e:
            log.exception(f"💥 Döngü hatası: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
