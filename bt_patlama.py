"""
"PATLAMA AVCISI" backtest'i — SAF 3 indikatör (mevcut bottan BAĞIMSIZ):
    1. SuperTrend (Factor=3, Period=10)
    2. Squeeze Momentum (LazyBear: BB 20/2, KC 20/1.5)
    3. VWAP (günlük-çapa, TV varsayılanı)

KURALLAR (kullanıcının tanımladığı gibi):
  LONG : close>VWAP  VE  SuperTrend yeşil (close>ST)  VE  squeeze SIÇRAMA
         (son N barda sıkışma bitti) VE momentum val>0 & yükseliyor.
  SHORT: aynısının aynası.
  ÇIKIŞ/STOP: SuperTrend ters dönerse (flip) pozisyonu kapat. (Trailing yapı.)
  Opsiyonel kısmi-TP kapalı (saf test) — PARTIAL=False.

Test evreni: MAJÖRLER (likit) + VOLATİL (botun seçtiği tip) → her ikisi ayrı + toplam.
Maliyet/kaldıraç: mevcut testlerle AYNI (karşılaştırılabilir olsun). TF=1h.

DÜRÜST sınır: aynı-bar sinyal/çıkış iyimser; volatil kova "bugün volatil"
coinlerin geçmişi (hafif ileriye-bakış); kısa geçmişli coinler atlanır.
Karşılaştırma hedefi: mevcut 5-koşullu strateji baseline PF ~1.40.

Çalıştırma:  python bt_patlama.py   (Binance erişimi olan makinede)
API anahtarı GEREKMEZ, emir YOK.
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb
import bt_coins

cfg = tb.CONFIG
log = tb.log

# ── Parametreler ──
ST_PERIOD, ST_FACTOR = 10, 3.0
BB_LEN, BB_MULT      = 20, 2.0
KC_LEN, KC_MULT      = 20, 1.5
SQZ_FIRE_LOOKBACK    = 3        # son kaç barda sıkışma bitmiş olmalı
MAX_HOLD_BARS        = 200      # güvenlik tavanı (ST flip gelmezse)
PARTIAL              = False    # saf test: kısmi-TP kapalı
MIN_HISTORY          = 250


# ─────────────────────────────────────────────────────────────
# İNDİKATÖRLER
# ─────────────────────────────────────────────────────────────

def supertrend(df, period=ST_PERIOD, factor=ST_FACTOR):
    """Standart SuperTrend → yön serisi (+1 yeşil/yukarı, -1 kırmızı/aşağı)."""
    atr = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"],
                                            window=period).average_true_range()
    hl2 = (df["high"] + df["low"]) / 2
    ub = hl2 + factor * atr
    lb = hl2 - factor * atr
    close = df["close"].values
    ubv, lbv = ub.values, lb.values
    n = len(df)
    fub = np.full(n, np.nan); flb = np.full(n, np.nan)
    st  = np.full(n, np.nan); dirn = np.zeros(n, dtype=int)
    for i in range(n):
        if i == 0 or np.isnan(atr.values[i]):
            fub[i] = ubv[i]; flb[i] = lbv[i]; st[i] = ubv[i]; dirn[i] = -1
            continue
        fub[i] = ubv[i] if (ubv[i] < fub[i-1] or close[i-1] > fub[i-1]) else fub[i-1]
        flb[i] = lbv[i] if (lbv[i] > flb[i-1] or close[i-1] < flb[i-1]) else flb[i-1]
        if st[i-1] == fub[i-1]:
            st[i] = fub[i] if close[i] <= fub[i] else flb[i]
        else:
            st[i] = flb[i] if close[i] >= flb[i] else fub[i]
        dirn[i] = 1 if st[i] == flb[i] else -1
    return pd.Series(dirn, index=df.index)


def _linreg_endpoint(series, window):
    x = np.arange(window); xm = x.mean(); denom = ((x - xm) ** 2).sum()
    def f(y):
        ym = y.mean(); slope = ((x - xm) * (y - ym)).sum() / denom
        return (ym - slope * xm) + slope * (window - 1)
    return series.rolling(window).apply(f, raw=True)


def squeeze(df):
    """LazyBear Squeeze → (sqz_on seri, momentum val seri)."""
    c = df["close"]
    basis = c.rolling(BB_LEN).mean()
    dev   = BB_MULT * c.rolling(BB_LEN).std(ddof=0)
    upBB, loBB = basis + dev, basis - dev
    ma = c.rolling(KC_LEN).mean()
    rng = (df["high"] - df["low"]).rolling(KC_LEN).mean()
    upKC, loKC = ma + KC_MULT * rng, ma - KC_MULT * rng
    sqz_on = (loBB > loKC) & (upBB < upKC)
    highest = df["high"].rolling(KC_LEN).max()
    lowest  = df["low"].rolling(KC_LEN).min()
    m1  = ((highest + lowest) / 2 + c.rolling(KC_LEN).mean()) / 2
    val = _linreg_endpoint(c - m1, KC_LEN)
    return sqz_on, val


def vwap_series(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.normalize()
    return (tp * df["volume"]).groupby(day).cumsum() / df["volume"].groupby(day).cumsum().replace(0, np.nan)


# ─────────────────────────────────────────────────────────────
# SİNYAL + SİMÜLASYON
# ─────────────────────────────────────────────────────────────

def build_signals(df):
    """Her bar için LONG/SHORT/None sinyali (kurallar birebir)."""
    d   = supertrend(df)
    son, val = squeeze(df)
    vw  = vwap_series(df)
    n = len(df)
    fired = np.zeros(n, dtype=bool)          # son N barda sıkışma bitti mi
    son_v = son.values
    for i in range(1, n):
        w0 = max(1, i - SQZ_FIRE_LOOKBACK)
        # bir önceki barlarda on iken şimdi off → release
        fired[i] = (not son_v[i]) and any(son_v[j] for j in range(w0, i))
    close = df["close"].values; vwv = vw.values; valv = val.values
    sig = [None] * n
    for i in range(KC_LEN + 2, n):
        if np.isnan(vwv[i]) or np.isnan(valv[i]):
            continue
        long_ok  = (close[i] > vwv[i]) and (d.iloc[i] == 1) and fired[i] and \
                   (valv[i] > 0) and (valv[i] > valv[i-1])
        short_ok = (close[i] < vwv[i]) and (d.iloc[i] == -1) and fired[i] and \
                   (valv[i] < 0) and (valv[i] < valv[i-1])
        if long_ok:  sig[i] = "LONG"
        elif short_ok: sig[i] = "SHORT"
    return sig, d


def simulate(df, i, side, d):
    """ST flip olana kadar tut, flip'te kapat (veya tavan bar)."""
    lev  = int(cfg["leverage"])
    cost = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * lev
    entry = float(df["close"].iloc[i])
    n = len(df)
    want = 1 if side == "LONG" else -1
    for k in range(1, MAX_HOLD_BARS + 1):
        j = i + k
        if j >= n:
            j = n - 1
            break
        if int(d.iloc[j]) != want:      # SuperTrend ters döndü → çık
            break
    exit_px = float(df["close"].iloc[j])
    roi = (exit_px / entry - 1) * 100 * lev if side == "LONG" else (entry / exit_px - 1) * 100 * lev
    return roi - cost, k


def run_symbol(df):
    if len(df) < MIN_HISTORY:
        return []
    sig, d = build_signals(df)
    trades = []
    j_free = 0
    for i in range(len(df) - 1):
        if i < j_free or sig[i] is None:
            continue
        net, bars = simulate(df, i, sig[i], d)
        trades.append({"side": sig[i], "net": net, "bars": bars})
        j_free = i + bars + 1          # pozisyon kapanana kadar yeni açma
    return trades


def stats(trades):
    if not trades:
        return None
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades),
            "aw": (gw/len(w) if w else 0), "al": (-gl/len(l) if l else 0),
            "avg_bars": np.mean([t["bars"] for t in trades])}


def run_bucket(ex, name, symbols):
    per = {}
    allt = []
    for sym in symbols:
        try:
            df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
        except Exception as e:
            log.warning(f"   [{sym}] veri hatası: {e}"); continue
        tr = run_symbol(df)
        if tr:
            per[sym.split("/")[0]] = sum(t["net"] for t in tr), len(tr)
            allt.extend(tr)
        log.info(f"   [{sym.split('/')[0]:8}] {len(tr)} işlem")
    s = stats(allt)
    if not s:
        log.info(f"  [{name}] hiç işlem yok"); return None
    log.info("\n" + "─" * 60)
    log.info(f"  📦 {name}  ({len(per)} coin, {s['n']} işlem, ort {s['avg_bars']:.0f} bar tutuş)")
    log.info(f"     WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  net={s['net']:+.1f}%  "
             f"ort+={s['aw']:+.1f}  ort-={s['al']:+.1f}")
    for c, (v, cnt) in sorted(per.items(), key=lambda x: x[1][0]):
        log.info(f"        {c:10} {v:>+7.1f}%  ({cnt})")
    return s


def main():
    log.info("📊 PATLAMA AVCISI (SuperTrend+Squeeze+VWAP) — saf 3 indikatör")
    log.info(f"   hedef: mevcut 5-koşullu baseline PF ~1.40'ı geçmek")
    ex = bt.connect()
    vol = bt_coins.pick_volatile(ex, bt_coins.VOLATILE_N, exclude=bt_coins.MAJORS)
    log.info("\n" + "═" * 60)
    sM = run_bucket(ex, "MAJÖRLER (likit)", bt_coins.MAJORS)
    sV = run_bucket(ex, "VOLATİL (botun seçtiği tip)", vol) if vol else None
    log.info("\n" + "═" * 60)
    log.info("  🎯 SONUÇ  (karşılaştırma: mevcut strateji PF ~1.40)")
    log.info("═" * 60)
    if sM: log.info(f"  MAJÖRLER : PF={sM['pf']:.2f}  WR=%{sM['wr']:.1f}  net={sM['net']:+.1f}%  ({sM['n']})")
    if sV: log.info(f"  VOLATİL  : PF={sV['pf']:.2f}  WR=%{sV['wr']:.1f}  net={sV['net']:+.1f}%  ({sV['n']})")
    best = max([s['pf'] for s in (sM, sV) if s], default=0)
    if best >= 1.55:
        log.info("  ✅ Baseline 1.40'ı NET geçiyor — ciddiye al, robustluk testi yap.")
    elif best >= 1.30:
        log.info("  ⚪ Baseline civarı — net üstünlük yok, değiştirmeye değmez.")
    else:
        log.info("  ❌ Baseline'ın ALTINDA — saf 3'lü daha kötü, mevcut kalsın.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
