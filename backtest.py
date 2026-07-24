"""
╔══════════════════════════════════════════════════════════════╗
║   📊 backtest.py — trade_bot stratejisini GEÇMİŞTE test eder  ║
╠══════════════════════════════════════════════════════════════╣

Ne yapar:
  • trade_bot.py'deki AYNI strateji beynini kullanır (calc_entry, get_signal,
    calc_trend, compute_sltp...). Kopyalamaz → import eder.
  • Geçmiş 1h mumları çeker, her kapanmış mumda sinyal üretir, pozisyonu
    SL / kısmi-kâr(@1R) / başabaş / koşucu-TP / zaman-limiti ile simüle eder.
  • Çıktı: toplam işlem, GERÇEK win rate (pozisyon bazında), net %, ortalama
    kazanç/zarar, profit factor, en iyi/kötü coinler.

Ne yapmaz:
  • Emir göndermez, para riski YOK. API anahtarı GEREKMEZ (halka açık veri).

⚠️  Yaklaşımlar (dürüst sınırlar):
  • 5m/15m alt-zaman teyidi (LTF) backtest'te KAPALI (geçmiş hizalaması zor).
    → Canlıda LTF birkaç girişi daha eler; backtest biraz iyimser olabilir.
  • Dinamik volatil coin tarayıcı geçmişte çalıştırılamaz → SABİT coin listesi
    (aşağıda BT_SYMBOLS) test edilir. Listeyi kendi coinlerinle değiştir.
  • Aynı mumda hem TP hem SL varsa: önce kısmi-TP, sonra SL varsayılır (hafif iyimser).

Çalıştırma:  python backtest.py
Ayarlar için aşağıdaki BT_* değişkenlerini düzenle.
"""

import ccxt
import pandas as pd

import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

# ─────────────────────────────────────────────────────────────
# BACKTEST AYARLARI
# ─────────────────────────────────────────────────────────────

# Test edilecek coinler (sabit liste — dinamik tarayıcı geçmişte çalışmaz).
# İstediğin coinleri ekle/çıkar. Uzun geçmişi olan likit coinler daha sağlıklı.
BT_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT",
    "ADA/USDT:USDT", "DOT/USDT:USDT", "KAITO/USDT:USDT", "GALA/USDT:USDT",
]

BT_1H_LIMIT   = 1000     # kaç 1h mum test edilsin (~42 gün). Borsa limiti ~1000-1500.
BT_4H_LIMIT   = 500      # 4h geçmişi (EMA200 için ≥214 gerekli — direkt çekilir)
BT_1D_LIMIT   = 400      # 1d geçmişi (rejim/EMA200 için)
BT_WARMUP     = 50       # ilk N 1h mumu atla (garanti ısınma)
BT_WINDOW     = 320      # her mumda strateji beynine verilecek geriye dönük 1h penceresi
BT_USE_BTC    = True     # BTC filtresi backtest'te de uygulansın mı (gerçekçi)

# ─────────────────────────────────────────────────────────────
# VERİ
# ─────────────────────────────────────────────────────────────

def connect() -> ccxt.binance:
    ex = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True})
    ex.load_markets()
    return ex


def fetch_tf(ex, symbol, tf, limit) -> pd.DataFrame:
    raw = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("ts", inplace=True)
    return df

# ─────────────────────────────────────────────────────────────
# POZİSYON SİMÜLASYONU (kısmi-kâr + başabaş + koşucu-TP + zaman)
# ─────────────────────────────────────────────────────────────

def simulate_position(df1h, i, side, entry, atr):
    """i. mumun KAPANIŞINDA açılan pozisyonu ileri mumlarla simüle eder.
    Döner: (net_roi_pct_kaldıraçlı, reason, bars_held) — net_roi TÜM pozisyon (kısmi+koşucu)."""
    lev  = int(cfg["leverage"])
    cost = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * lev   # gidiş-dönüş maliyet (kaldıraçlı %)
    sl, _tp_ignored = tb.compute_sltp(entry, atr, side)
    sl_dist = abs(entry - sl)
    if sl_dist <= 0:
        return None

    partial = cfg.get("partial_tp_enabled", False)
    frac    = cfg["partial_tp_frac"] if partial else 0.0
    rr      = cfg["partial_runner_rr"] if partial else cfg["rr_ratio"]
    cost_fr = (cfg["commission"] + cfg["slippage"]) * 2

    if side == "LONG":
        tp2 = entry + sl_dist * rr + entry * cost_fr
        tp1 = entry + sl_dist * cfg["partial_tp_r"] if partial else None
        be  = entry * 1.0001
    else:
        tp2 = entry - sl_dist * rr - entry * cost_fr
        tp1 = entry - sl_dist * cfg["partial_tp_r"] if partial else None
        be  = entry * 0.9999

    def roi(exit_px, portion):
        if side == "LONG":
            p = (exit_px / entry - 1) * 100 * lev
        else:
            p = (entry / exit_px - 1) * 100 * lev
        return (p - cost) * portion

    max_bars = max(1, int(cfg["max_pos_hours"]))   # 1h mum = 1 saat
    partial_done = False
    realized = 0.0
    n = len(df1h)

    for k in range(1, max_bars + 1):
        j = i + k
        if j >= n:
            break
        bar = df1h.iloc[j]
        hi, lo = float(bar["high"]), float(bar["low"])
        cur_sl = be if partial_done else sl

        if side == "LONG":
            if partial and not partial_done and hi >= tp1:     # kısmi-kâr @1R
                realized += roi(tp1, frac); partial_done = True
            if lo <= cur_sl:                                    # SL / başabaş
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(cur_sl, rem)
                reason = "BREAKEVEN" if (partial_done and cur_sl >= entry) else "STOP_LOSS"
                return realized, reason, k
            if hi >= tp2:                                       # koşucu hedef
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(tp2, rem)
                return realized, "TAKE_PROFIT", k
        else:
            if partial and not partial_done and lo <= tp1:
                realized += roi(tp1, frac); partial_done = True
            if hi >= cur_sl:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(cur_sl, rem)
                reason = "BREAKEVEN" if (partial_done and cur_sl <= entry) else "STOP_LOSS"
                return realized, reason, k
            if lo <= tp2:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(tp2, rem)
                return realized, "TAKE_PROFIT", k

    # Zaman limiti → son mum kapanışında kapat
    j = min(n - 1, i + max_bars)
    exit_px = float(df1h.iloc[j]["close"])
    rem = (1 - frac) if partial_done else 1.0
    realized += roi(exit_px, rem)
    return realized, "TIME_LIMIT", (j - i)

# ─────────────────────────────────────────────────────────────
# TEK COİN BACKTEST
# ─────────────────────────────────────────────────────────────

def backtest_symbol(ex, symbol, df1h, df4h, df1d, btc1h):
    trades = []
    n = len(df1h)
    j_next_free = 0   # bu bardan önce yeni pozisyon açılamaz (mevcut açık)

    for i in range(BT_WARMUP, n - 1):
        if i < j_next_free:
            continue
        now = df1h.index[i] + pd.Timedelta(hours=1)   # i. mumun KAPANIŞ zamanı (lookahead yok)

        # Kapanmış üst zaman dilimi mumları (forming olanı dahil etme)
        d4 = df4h[df4h.index + pd.Timedelta(hours=4) <= now]
        dd = df1d[df1d.index + pd.Timedelta(days=1)  <= now]
        d1 = df1h.iloc[max(0, i - BT_WINDOW): i + 1]
        if len(d4) < cfg["ema_trend"] + cfg["adx_period"] or len(dd) < 5 or len(d1) < 60:
            continue

        try:
            daily = tb.calc_daily_trend(dd.copy())
            trend = tb.calc_trend(d4.copy())
            if trend is None:
                continue
            entry = tb.calc_entry(d1.copy())
            if entry is None:
                continue
            entry_trend = tb.calc_entry_trend(d1.copy())
        except Exception:
            continue

        # BTC 1h değişimi (filtre için)
        btc_chg = 0.0
        if BT_USE_BTC and btc1h is not None and len(btc1h) > i:
            try:
                bwin = btc1h[btc1h.index <= df1h.index[i]]
                if len(bwin) >= 2:
                    btc_chg = (float(bwin["close"].iloc[-1]) / float(bwin["close"].iloc[-2]) - 1)
            except Exception:
                btc_chg = 0.0

        # LTF backtest'te kapalı → tf5=tf15=NONE (engellemez)
        signal = tb.get_signal(trend, entry, daily, btc_chg, entry_trend, "NONE", "NONE")

        if signal in ("LONG", "SHORT"):
            price = float(d1["close"].iloc[-1])
            res = simulate_position(df1h, i, signal, price, entry["atr"])
            if res is None:
                continue
            net, reason, bars = res
            trades.append({"time": df1h.index[i], "symbol": symbol.split("/")[0],
                           "side": signal, "net": net, "reason": reason, "bars": bars})
            j_next_free = i + bars + 1   # pozisyon kapanana kadar yeni açma (tek pozisyon/coin)

    return trades

# ─────────────────────────────────────────────────────────────
# İSTATİSTİK
# ─────────────────────────────────────────────────────────────

def report(trades):
    if not trades:
        log.info("⚠️  Hiç işlem üretilmedi (period/coin/filtre çok kısıtlayıcı olabilir).")
        return
    n = len(trades)
    wins = [t for t in trades if t["net"] > 0]
    loss = [t for t in trades if t["net"] <= 0]
    gross_win = sum(t["net"] for t in wins)
    gross_loss = -sum(t["net"] for t in loss)
    net = sum(t["net"] for t in trades)
    wr = len(wins) / n * 100
    avg_w = gross_win / len(wins) if wins else 0
    avg_l = -gross_loss / len(loss) if loss else 0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    expectancy = net / n

    from collections import defaultdict, Counter
    byr = Counter(t["reason"] for t in trades)
    byc = defaultdict(float)
    for t in trades:
        byc[t["symbol"]] += t["net"]

    log.info("\n" + "═" * 56)
    log.info("  📊 BACKTEST SONUCU  (net = kaldıraçlı ROI %, pozisyon başına)")
    log.info("═" * 56)
    log.info(f"  İşlem sayısı   : {n}")
    log.info(f"  GERÇEK Win Rate: %{wr:.1f}  ({len(wins)}W / {len(loss)}L)")
    log.info(f"  Net (toplam)   : {net:+.1f}%   (işlem başına beklenti: {expectancy:+.2f}%)")
    log.info(f"  Ort. kazanç    : {avg_w:+.2f}%     Ort. zarar: {avg_l:+.2f}%")
    log.info(f"  Kazanç/Zarar   : {(avg_w/abs(avg_l) if avg_l else 0):.2f} : 1")
    log.info(f"  Profit Factor  : {pf:.2f}   (>1 kârlı, >1.3 iyi)")
    log.info(f"  Çıkış nedenleri: " + "  ".join(f"{k}={v}" for k, v in byr.most_common()))
    log.info("  ── Coin bazında net ──")
    for c, v in sorted(byc.items(), key=lambda x: -x[1]):
        log.info(f"     {c:8} {v:+7.1f}%")
    log.info("═" * 56)
    log.info("  Not: net % kaldıraçlı. $ karşılığı ≈ (marj × net/100). LTF kapalı,")
    log.info("       sabit coin listesi — canlı sonuç birebir aynı olmayabilir.")
    log.info("═" * 56 + "\n")

# ─────────────────────────────────────────────────────────────
# ANA
# ─────────────────────────────────────────────────────────────

def main():
    log.info("📊 Backtest başlıyor — strateji beyni: trade_bot.py (aynı)")
    log.info(f"   Coinler: {len(BT_SYMBOLS)}   1h mum: {BT_1H_LIMIT}   LTF: kapalı")
    ex = connect()

    # BTC referansı (filtre için)
    btc1h = None
    if BT_USE_BTC:
        try:
            btc1h = fetch_tf(ex, "BTC/USDT:USDT", "1h", BT_1H_LIMIT)
        except Exception as e:
            log.warning(f"⚠️  BTC verisi çekilemedi, BTC filtresi backtest'te atlanacak: {e}")

    all_trades = []
    for sym in BT_SYMBOLS:
        try:
            df1h = fetch_tf(ex, sym, "1h", BT_1H_LIMIT)
            df4h = fetch_tf(ex, sym, "4h", BT_4H_LIMIT)   # EMA200 için direkt (resample değil)
            df1d = fetch_tf(ex, sym, "1d", BT_1D_LIMIT)
            if len(df1h) < BT_WARMUP + 50:
                log.info(f"   [{sym}] yetersiz geçmiş ({len(df1h)} mum), atlandı")
                continue
            tr = backtest_symbol(ex, sym, df1h, df4h, df1d, btc1h)
            log.info(f"   [{sym.split('/')[0]:8}] {len(tr)} işlem")
            all_trades.extend(tr)
        except Exception as e:
            log.warning(f"   [{sym}] backtest hatası, atlandı: {e}")

    report(all_trades)


if __name__ == "__main__":
    main()
