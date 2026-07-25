"""
ADAY STRATEJİ backtest'i — mevcut 5-koşullu skoru şu üçlüyle değiştirir:
    Squeeze Momentum (LazyBear TTM) + VWAP (günlük-çapa) + StochRSI K/D crossover

Amaç: canlıya DOKUNMADAN, mevcut baseline (PF ~1.40) ile A/B karşılaştırmak.
  • AYNI coinler, AYNI yüksek-TF gate'ler (4h yön+ADX, 1d rejim, adx_max),
    AYNI çıkış simülasyonu (backtest.simulate_position) → tek değişen: GİRİŞ skoru.
  • Bu sayede fark tamamen "giriş kalitesi" farkıdır, elmayla elma.

Rapor:
  • Aday: min 2/3 ve min 3/3 için ayrı PF (3 indikatör olduğu için maks skor 3'tür;
    "min skor 4" matematiksel olarak imkansız — o yüzden 3/3 en katısı).
  • İki-yarı robustluk: her coinin ilk yarısı vs ikinci yarısı ayrı PF
    (bir yarıda kâr diğerinde zarar = overfit, güvenme).

Çalıştırma:  python bt_candidate.py     (Binance erişimi olan makinede)
API anahtarı GEREKMEZ, emir YOK, sadece geçmiş veri okur.
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

# ── Aday indikatör parametreleri ──
SQZ_LEN   = 20      # BB & KC & momentum penceresi
SQZ_MULT  = 1.5     # Keltner çarpanı (kullanılmıyor ama referans)
STOCH_CROSS_LOOKBACK = 3   # son N mumda K, D'yi kesmiş mi (taze crossover)


# ─────────────────────────────────────────────────────────────
# ADAY GİRİŞ İNDİKATÖRLERİ (kendi içinde, trade_bot.calc_entry'den bağımsız)
# ─────────────────────────────────────────────────────────────

def _linreg_endpoint(series: pd.Series, window: int) -> pd.Series:
    """Her nokta için son `window` mumun lineer regresyon UÇ değeri (LazyBear val)."""
    x = np.arange(window)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()
    def f(y):
        ym = y.mean()
        slope = ((x - xm) * (y - ym)).sum() / denom
        intercept = ym - slope * xm
        return intercept + slope * (window - 1)   # son bar
    return series.rolling(window).apply(f, raw=True)


def squeeze_momentum_dir(df: pd.DataFrame) -> str:
    """LazyBear Squeeze Momentum histogram yönü (son bar)."""
    c = df["close"]
    highest = df["high"].rolling(SQZ_LEN).max()
    lowest  = df["low"].rolling(SQZ_LEN).min()
    sma_c   = c.rolling(SQZ_LEN).mean()
    m1      = ((highest + lowest) / 2 + sma_c) / 2
    val     = _linreg_endpoint(c - m1, SQZ_LEN)
    v = val.iloc[-1]
    if pd.isna(v):
        return "NONE"
    return "LONG" if v > 0 else "SHORT" if v < 0 else "NONE"


def vwap_dir(df: pd.DataFrame) -> str:
    """Günlük-çapa VWAP'a göre yön (fiyat üstünde=LONG)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.normalize()
    pv = (tp * df["volume"]).groupby(day).cumsum()
    vv = df["volume"].groupby(day).cumsum()
    vwap = pv / vv.replace(0, np.nan)
    if pd.isna(vwap.iloc[-1]):
        return "NONE"
    price = float(df["close"].iloc[-1])
    return "LONG" if price > float(vwap.iloc[-1]) else "SHORT"


def stochrsi_cross_dir(df: pd.DataFrame) -> str:
    """StochRSI K/D crossover yönü — K>D ve son N mumda taze kesişim olmuş."""
    st = tb.ta.momentum.StochRSIIndicator(
        df["close"], window=cfg["stoch_period"],
        smooth1=cfg["stoch_smooth_k"], smooth2=cfg["stoch_smooth_d"])
    k = (st.stochrsi_k() * 100).dropna()
    d = (st.stochrsi_d() * 100).dropna()
    if len(k) < STOCH_CROSS_LOOKBACK + 2:
        return "NONE"
    kl, dl = float(k.iloc[-1]), float(d.iloc[-1])
    # taze crossover: son N mumda ters durumdan mevcut duruma geçmiş mi
    up = dn = False
    for i in range(1, STOCH_CROSS_LOOKBACK + 1):
        if k.iloc[-i] > d.iloc[-i] and k.iloc[-i-1] <= d.iloc[-i-1]:
            up = True
        if k.iloc[-i] < d.iloc[-i] and k.iloc[-i-1] >= d.iloc[-i-1]:
            dn = True
    if kl > dl and up:
        return "LONG"
    if kl < dl and dn:
        return "SHORT"
    # taze kesişim yoksa: sadece durum (post-crossover) — daha çok sinyal için
    return "LONG" if kl > dl else "SHORT"


def candidate_score(df1h: pd.DataFrame, direction: str):
    """4h yönüne (direction) uyan indikatör sayısını döndürür (0..3) + atr."""
    sq = squeeze_momentum_dir(df1h)
    vw = vwap_dir(df1h)
    sr = stochrsi_cross_dir(df1h)
    dirs = [sq, vw, sr]
    score = sum(1 for x in dirs if x == direction)
    return score, {"squeeze": sq, "vwap": vw, "stoch": sr}


# ─────────────────────────────────────────────────────────────
# GİRİŞ TOPLAMA — baseline'ın gate'lerini korur, skoru üçlüyle değiştirir
# ─────────────────────────────────────────────────────────────

def collect_candidate(sym, df1h, df4h, df1d, btc1h):
    entries = []
    n = len(df1h)
    j_free = 0
    cache = {"n4": -1, "n1d": -1, "trend": None, "daily": None}
    # ATR'yi baseline ile aynı şekilde calc_entry'den al (çıkış SL'i aynı olsun)
    for i in range(bt.BT_WARMUP, n - 1):
        if i < j_free:
            continue
        now = df1h.index[i] + pd.Timedelta(hours=1)
        d4 = df4h[df4h.index + pd.Timedelta(hours=4) <= now]
        dd = df1d[df1d.index + pd.Timedelta(days=1) <= now]
        if len(d4) < cfg["ema_trend"] + cfg["adx_period"] or len(dd) < 5:
            continue
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
        d = trend["direction"]
        # ── AYNI RİSK GATE'LERİ (baseline get_signal ile birebir) ──
        if d == "NONE" or not trend["adx_ok"]:
            continue
        if cfg.get("adx_max") and trend["adx"] >= cfg["adx_max"]:
            continue
        if daily != "NONE" and daily != d:
            continue

        d1 = df1h.iloc[max(0, i - bt.BT_WINDOW): i + 1]
        if len(d1) < max(SQZ_LEN, cfg["stoch_period"]) + 5:
            continue
        # ATR (baseline calc_entry ile aynı hesap) → çıkış SL tutarlı olsun
        try:
            ent = tb.calc_entry(d1.copy())
            if ent is None:
                continue
            atr = ent["atr"]
        except Exception:
            continue

        score, parts = candidate_score(d1.copy(), d)
        if score >= 2:   # min 2/3 topla; raporda 3/3 ayrıca süzülür
            price = float(d1["close"].iloc[-1])
            entries.append({"sym": sym.split("/")[0], "i": i, "side": d,
                            "price": price, "atr": atr, "score": score,
                            "half": 0 if i < n // 2 else 1})
            j_free = i + max(1, int(cfg["max_pos_hours"])) + 1
    return entries


def sim(entries, dfmap):
    out = []
    for e in entries:
        res = bt.simulate_position(dfmap[e["sym"]], e["i"], e["side"], e["price"], e["atr"])
        if res is None:
            continue
        net, reason, bars = res
        out.append({**e, "net": net, "reason": reason})
    return out


def pf(trades):
    if not trades:
        return None
    n = len(trades)
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    return {"n": n, "wr": len(w)/n*100, "pf": (gw/gl if gl > 0 else 99),
            "net": sum(t["net"] for t in trades),
            "aw": (gw/len(w) if w else 0), "al": (-gl/len(l) if l else 0)}


def line(label, trades):
    s = pf(trades)
    if not s:
        log.info(f"  {label:20} yok"); return
    log.info(f"  {label:20} n={s['n']:>4}  WR=%{s['wr']:>4.1f}  PF={s['pf']:>5.2f}  "
             f"net={s['net']:>+7.1f}%  ort+={s['aw']:>+5.1f}  ort-={s['al']:>+5.1f}")


def main():
    log.info("📊 ADAY STRATEJİ backtest'i — Squeeze + VWAP + StochRSI-cross")
    ex = bt.connect()
    dfmap, meta, btc1h = bt.load_data(ex)
    all_e = []
    for sym, (df1h, df4h, df1d) in meta.items():
        e = collect_candidate(sym, df1h, df4h, df1d, btc1h)
        log.info(f"   [{sym.split('/')[0]:8}] {len(e)} sinyal (min 2/3)")
        all_e.extend(e)
    trades = sim(all_e, dfmap)
    log.info("\n" + "═" * 74)
    log.info(f"  ADAY: Squeeze+VWAP+StochRSI  ({len(bt.BT_SYMBOLS)} coin, {bt.BT_1H_LIMIT} saat)")
    log.info(f"  (karşılaştırma hedefi: mevcut baseline PF ~1.40)")
    log.info("═" * 74)
    line("min 2/3 (HEPSİ)", trades)
    line("min 3/3 (katı)",  [t for t in trades if t["score"] >= 3])
    log.info("  ── İki-yarı robustluk (min 2/3) ──")
    line("1. yarı", [t for t in trades if t["half"] == 0])
    line("2. yarı", [t for t in trades if t["half"] == 1])
    log.info("═" * 74)
    log.info("  Yorum: min 2/3 VE min 3/3 ikisi de baseline 1.40'ı NET geçmiyorsa,")
    log.info("         VE iki yarı tutarlı değilse → aday daha iyi DEĞİL, değiştirme.")


if __name__ == "__main__":
    main()
