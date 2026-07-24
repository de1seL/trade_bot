"""
╔══════════════════════════════════════════════════════════════╗
║   📊 backtest.py — stratejiyi GEÇMİŞTE test + SWEEP eder      ║
╠══════════════════════════════════════════════════════════════╣

Ne yapar:
  • trade_bot.py'deki AYNI strateji beynini kullanır (calc_entry, get_signal,
    calc_trend...). Kopyalamaz → import eder (tek kaynak).
  • Girişleri BİR KEZ hesaplar (yavaş kısım), sonra çıkış ayarlarını (R:R,
    kısmi-kâr...) SANİYELER içinde tarar (sweep) → en iyi ayarı rakamla bulur.
  • Çıktı: gerçek (pozisyon-bazlı) WR, net%, ort kazanç/zarar, Profit Factor.

İKİ MOD (aşağıda BT_SWEEP ile seçilir):
  • BT_SWEEP = None            → sadece mevcut config'i test et (baseline)
  • BT_SWEEP = ("param",[...]) → o parametreyi verilen değerlerde tara,
                                  her biri için PF'yi yan yana göster
    Örnek çıkış-parametre taramaları:
      ("partial_runner_rr", [1.5, 2.0, 2.5, 3.0])
      ("partial_tp_enabled", [True, False])
      ("atr_sl_mult", [1.0, 1.3, 1.6, 2.0])
      ("rr_ratio", [1.5, 2.0, 2.5])          # partial kapalıyken tek TP hedefi
    ⚠️ Sadece ÇIKIŞ parametreleri hızlı taranır (girişler değişmez). Giriş
       parametreleri (min_conditions, adx... indikatörler) için BT_SWEEP_ENTRY=True yap
       → her değer için baştan hesaplar (yavaş ama doğru).

Sınırlar (dürüst): LTF(5m/15m) kapalı, sabit coin listesi, aynı-mum TP/SL iyimser.
API anahtarı GEREKMEZ, emir YOK.

Çalıştırma:  python backtest.py
"""

import ccxt
import pandas as pd

import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

# ─────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────

BT_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT",
    "ADA/USDT:USDT", "DOT/USDT:USDT", "KAITO/USDT:USDT", "GALA/USDT:USDT",
]

BT_1H_LIMIT = 1000
BT_4H_LIMIT = 500
BT_1D_LIMIT = 400
BT_WARMUP   = 50
BT_WINDOW   = 320
BT_USE_BTC  = True

# ── SWEEP (tarama) ─────────────────────────────────────────────
# None → sadece baseline.
# (param,[değerler]) → tek tarama.
# [ (p1,[..]), (p2,[..]) ] → LİSTE: girişler bir kez toplanır, hepsi arka
#   arkaya taranır (tek çalıştırmada çıkış optimizasyonunun tamamı).
# Çıkış sweep'i bitti → yeni ayarlar (sl_mult=1.0, runner_rr=3.0) uygulandı.
# Şimdi None: yeni config'in BİRLEŞİK PF'sini gör (kombinasyon doğrulaması).
BT_SWEEP = None
# Sıradaki tur (giriş/indikatör ablation) için örnekler:
#   BT_SWEEP = ("min_conditions", [2, 3, 4]);       BT_SWEEP_ENTRY = True
#   BT_SWEEP = ("macd_in_score", [True, False]);    BT_SWEEP_ENTRY = True
#   BT_SWEEP = ("adx_max", [40, 44, 48, 100]);      BT_SWEEP_ENTRY = True
# Giriş parametresi mi tarıyorsun? (min_conditions, adx_max, indikatör flag'i...)
# True yaparsan her değer için girişler baştan hesaplanır (yavaş). Sadece TEK
# (param,[değerler]) ile birlikte kullan (liste ile değil).
BT_SWEEP_ENTRY = False

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
# ÇIKIŞ SİMÜLASYONU (kısmi-kâr + başabaş + koşucu-TP + zaman)
# ─────────────────────────────────────────────────────────────

def simulate_position(df1h, i, side, entry, atr):
    """i. mumun kapanışında açılan pozisyonu ileri mumlarla simüle eder.
    CONFIG'in ÇIKIŞ ayarlarını okur → sweep bunları değiştirip yeniden çağırır."""
    lev  = int(cfg["leverage"])
    cost = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * lev
    sl, _ = tb.compute_sltp(entry, atr, side)
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
        p = (exit_px / entry - 1) * 100 * lev if side == "LONG" else (entry / exit_px - 1) * 100 * lev
        return (p - cost) * portion

    max_bars = max(1, int(cfg["max_pos_hours"]))
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
            if partial and not partial_done and hi >= tp1:
                realized += roi(tp1, frac); partial_done = True
            if lo <= cur_sl:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(cur_sl, rem)
                return realized, ("BREAKEVEN" if (partial_done and cur_sl >= entry) else "STOP_LOSS"), k
            if hi >= tp2:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(tp2, rem)
                return realized, "TAKE_PROFIT", k
        else:
            if partial and not partial_done and lo <= tp1:
                realized += roi(tp1, frac); partial_done = True
            if hi >= cur_sl:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(cur_sl, rem)
                return realized, ("BREAKEVEN" if (partial_done and cur_sl <= entry) else "STOP_LOSS"), k
            if lo <= tp2:
                rem = (1 - frac) if partial_done else 1.0
                realized += roi(tp2, rem)
                return realized, "TAKE_PROFIT", k

    j = min(n - 1, i + max_bars)
    exit_px = float(df1h.iloc[j]["close"])
    rem = (1 - frac) if partial_done else 1.0
    realized += roi(exit_px, rem)
    return realized, "TIME_LIMIT", (j - i)

# ─────────────────────────────────────────────────────────────
# GİRİŞ TOPLAMA (yavaş kısım — BİR KEZ çalışır)
# ─────────────────────────────────────────────────────────────

def collect_entries(sym, df1h, df4h, df1d, btc1h):
    """Stratejiyi geçmişte çalıştırır, SADECE giriş sinyallerini toplar
    (çıkış simülasyonu YAPMAZ). 4h/1d trend cache'lenir → hız."""
    entries = []
    n = len(df1h)
    j_free = 0
    cache = {"n4": -1, "n1d": -1, "trend": None, "daily": None}

    for i in range(BT_WARMUP, n - 1):
        if i < j_free:
            continue
        now = df1h.index[i] + pd.Timedelta(hours=1)
        d4 = df4h[df4h.index + pd.Timedelta(hours=4) <= now]
        dd = df1d[df1d.index + pd.Timedelta(days=1) <= now]
        if len(d4) < cfg["ema_trend"] + cfg["adx_period"] or len(dd) < 5:
            continue

        # 4h/1d yalnızca yeni mum kapanınca yeniden hesapla (büyük hızlanma)
        if len(d4) != cache["n4"]:
            try: cache["trend"] = tb.calc_trend(d4.copy())
            except Exception: cache["trend"] = None
            cache["n4"] = len(d4)
        if len(dd) != cache["n1d"]:
            try: cache["daily"] = tb.calc_daily_trend(dd.copy())
            except Exception: cache["daily"] = "NONE"
            cache["n1d"] = len(dd)
        trend, daily = cache["trend"], cache["daily"]
        if trend is None:
            continue

        d1 = df1h.iloc[max(0, i - BT_WINDOW): i + 1]
        if len(d1) < 60:
            continue
        try:
            entry = tb.calc_entry(d1.copy())
            if entry is None:
                continue
            entry_trend = tb.calc_entry_trend(d1.copy())
        except Exception:
            continue

        btc_chg = 0.0
        if BT_USE_BTC and btc1h is not None:
            b = btc1h[btc1h.index <= df1h.index[i]]
            if len(b) >= 2:
                btc_chg = float(b["close"].iloc[-1]) / float(b["close"].iloc[-2]) - 1

        signal = tb.get_signal(trend, entry, daily, btc_chg, entry_trend, "NONE", "NONE")
        if signal in ("LONG", "SHORT"):
            price = float(d1["close"].iloc[-1])
            entries.append({"sym": sym.split("/")[0], "i": i, "side": signal,
                            "price": price, "atr": entry["atr"]})
            # pozisyon kapanana kadar yeni açma → kaba tahmin: max_pos_hours ilerlet
            j_free = i + max(1, int(cfg["max_pos_hours"])) + 1

    return entries

# ─────────────────────────────────────────────────────────────
# ÇIKIŞ DEĞERLENDİRME (hızlı — sweep bunu tekrar çağırır)
# ─────────────────────────────────────────────────────────────

def simulate_all(entries, dfmap):
    trades = []
    for e in entries:
        df1h = dfmap[e["sym"]]
        res = simulate_position(df1h, e["i"], e["side"], e["price"], e["atr"])
        if res is None:
            continue
        net, reason, bars = res
        trades.append({"symbol": e["sym"], "side": e["side"], "net": net, "reason": reason})
    return trades


def stats(trades):
    if not trades:
        return None
    n = len(trades)
    wins = [t["net"] for t in trades if t["net"] > 0]
    loss = [t["net"] for t in trades if t["net"] <= 0]
    gw = sum(wins); gl = -sum(loss)
    pf = (gw / gl) if gl > 0 else float("inf")
    return {"n": n, "wr": len(wins) / n * 100, "net": sum(t["net"] for t in trades),
            "avg_w": (gw / len(wins)) if wins else 0, "avg_l": (-gl / len(loss)) if loss else 0,
            "pf": pf, "trades": trades}


def report(s):
    from collections import Counter, defaultdict
    log.info("\n" + "═" * 56)
    log.info("  📊 BACKTEST SONUCU  (net = kaldıraçlı ROI %, pozisyon başına)")
    log.info("═" * 56)
    log.info(f"  İşlem sayısı   : {s['n']}")
    log.info(f"  GERÇEK Win Rate: %{s['wr']:.1f}")
    log.info(f"  Net (toplam)   : {s['net']:+.1f}%   (beklenti: {s['net']/s['n']:+.2f}%/işlem)")
    log.info(f"  Ort. kazanç    : {s['avg_w']:+.2f}%     Ort. zarar: {s['avg_l']:+.2f}%")
    log.info(f"  Profit Factor  : {s['pf']:.2f}   (>1 kârlı, >1.3 iyi, >1.5 harika)")
    byr = Counter(t["reason"] for t in s["trades"])
    log.info(f"  Çıkış nedenleri: " + "  ".join(f"{k}={v}" for k, v in byr.most_common()))
    byc = defaultdict(float)
    for t in s["trades"]:
        byc[t["symbol"]] += t["net"]
    log.info("  ── Coin bazında net ──")
    for c, v in sorted(byc.items(), key=lambda x: -x[1]):
        log.info(f"     {c:8} {v:+7.1f}%")
    log.info("═" * 56)

# ─────────────────────────────────────────────────────────────
# ANA
# ─────────────────────────────────────────────────────────────

def load_data(ex):
    dfmap = {}
    btc1h = None
    if BT_USE_BTC:
        try: btc1h = fetch_tf(ex, "BTC/USDT:USDT", "1h", BT_1H_LIMIT)
        except Exception as e: log.warning(f"⚠️  BTC verisi yok: {e}")
    meta = {}
    for sym in BT_SYMBOLS:
        try:
            df1h = fetch_tf(ex, sym, "1h", BT_1H_LIMIT)
            df4h = fetch_tf(ex, sym, "4h", BT_4H_LIMIT)
            df1d = fetch_tf(ex, sym, "1d", BT_1D_LIMIT)
            if len(df1h) < BT_WARMUP + 50:
                log.info(f"   [{sym}] yetersiz geçmiş, atlandı"); continue
            key = sym.split("/")[0]
            dfmap[key] = df1h
            meta[sym] = (df1h, df4h, df1d)
        except Exception as e:
            log.warning(f"   [{sym}] veri hatası: {e}")
    return dfmap, meta, btc1h


def gather_all_entries(meta, btc1h):
    entries = []
    for sym, (df1h, df4h, df1d) in meta.items():
        e = collect_entries(sym, df1h, df4h, df1d, btc1h)
        log.info(f"   [{sym.split('/')[0]:8}] {len(e)} sinyal")
        entries.extend(e)
    return entries


def main():
    log.info("📊 Backtest başlıyor — strateji beyni: trade_bot.py")
    log.info(f"   Coinler: {len(BT_SYMBOLS)}  1h mum: {BT_1H_LIMIT}  LTF: kapalı")
    ex = connect()
    dfmap, meta, btc1h = load_data(ex)

    if not BT_SWEEP:
        # ── BASELINE ──
        entries = gather_all_entries(meta, btc1h)
        s = stats(simulate_all(entries, dfmap))
        if s: report(s)
        else: log.info("⚠️  Hiç işlem yok.")
        return

    # Tek sweep de olsa listeye çevir → aynı kodla işle
    sweeps = BT_SWEEP if isinstance(BT_SWEEP, list) else [BT_SWEEP]

    def run_sweep(entries, param, values):
        _orig = cfg.get(param)
        log.info(f"\n🔬 SWEEP: '{param}'")
        log.info(f"  {'değer':>10} | {'işlem':>5} | {'WR%':>5} | {'net%':>7} | {'ort+':>6} | {'ort-':>7} | {'PF':>5}")
        log.info("  " + "-" * 62)
        best = None
        for v in values:
            cfg[param] = v
            if BT_SWEEP_ENTRY:                     # giriş paramı → baştan hesapla
                entries = gather_all_entries(meta, btc1h)
            s = stats(simulate_all(entries, dfmap))
            if s:
                log.info(f"  {str(v):>10} | {s['n']:>5} | {s['wr']:>5.1f} | {s['net']:>+7.1f} | {s['avg_w']:>+6.1f} | {s['avg_l']:>+7.1f} | {s['pf']:>5.2f}")
                if best is None or s["pf"] > best[1]:
                    best = (v, s["pf"])
        cfg[param] = _orig                          # değeri eski haline getir (bağımsız sweep)
        if best:
            log.info("  " + "-" * 62)
            log.info(f"  🏆 En iyi: {param} = {best[0]}  (PF {best[1]:.2f})")

    log.info(f"\n🔬 SWEEP MODU  ({len(sweeps)} parametre, giriş-tekrar={'AÇIK' if BT_SWEEP_ENTRY else 'kapalı'})")
    entries = gather_all_entries(meta, btc1h)        # girişleri BİR KEZ topla
    if not entries:
        log.info("⚠️  Hiç sinyal yok."); return
    for param, values in sweeps:
        run_sweep(entries, param, values)

    log.info("\n  Not: her sweep BAĞIMSIZ (diğer paramlar baseline'da). LTF kapalı,")
    log.info("       sabit coin listesi — canlı birebir aynı olmayabilir.")


if __name__ == "__main__":
    main()
