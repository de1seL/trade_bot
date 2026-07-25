"""
ADAY STRATEJİ backtest'i — 6 KOŞULLU skor:
    [ stoch, rsi, vol, st ]  (mevcut skordan KORUNAN 4 koşul)
  + [ Squeeze Momentum ]     (macd YERİNE)
  + [ VWAP günlük-çapa ]     (yeni 6. koşul)

Mevcut canlı skor 5 koşul: [stoch, rsi, macd, vol, st]  (EMA skorda değil, kapı).
Bu aday: macd → Squeeze değişir, VWAP eklenir → toplam 6 koşul. min 4 artık anlamlı.

A/B: canlıya DOKUNMADAN baseline (PF ~1.40) ile karşılaştırır.
  AYNI coinler, AYNI yüksek-TF gate'ler (4h yön+ADX, 1d rejim, adx_max),
  AYNI çıkış simülasyonu → tek değişen: skorun 2 koşulu.
  4 orijinal koşul (stoch/rsi/vol/st) doğrudan tb.calc_entry'den okunur → birebir aynı.

Rapor: min 3 / min 4 / min 5 için ayrı PF + iki-yarı robustluk.
Tetik: Squeeze==yön VEYA stoch==yön (macd yerine squeeze).

Çalıştırma:  python bt_candidate.py   (Binance erişimi olan makinede)
API anahtarı GEREKMEZ, emir YOK.
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

SQZ_LEN = 20
STOCH_CROSS_LOOKBACK = 3   # (bu adayda stoch skoru tb.calc_entry'den; cross ayrı kullanılmıyor)


# ── Yeni 2 indikatör (kendi içinde) ─────────────────────────────
def _linreg_endpoint(series: pd.Series, window: int) -> pd.Series:
    x = np.arange(window); xm = x.mean(); denom = ((x - xm) ** 2).sum()
    def f(y):
        ym = y.mean(); slope = ((x - xm) * (y - ym)).sum() / denom
        return (ym - slope * xm) + slope * (window - 1)
    return series.rolling(window).apply(f, raw=True)


def squeeze_dir(df: pd.DataFrame) -> str:
    c = df["close"]
    highest = df["high"].rolling(SQZ_LEN).max()
    lowest  = df["low"].rolling(SQZ_LEN).min()
    m1 = ((highest + lowest) / 2 + c.rolling(SQZ_LEN).mean()) / 2
    v = _linreg_endpoint(c - m1, SQZ_LEN).iloc[-1]
    if pd.isna(v): return "NONE"
    return "LONG" if v > 0 else "SHORT" if v < 0 else "NONE"


def vwap_dir(df: pd.DataFrame) -> str:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.normalize()
    vwap = (tp * df["volume"]).groupby(day).cumsum() / df["volume"].groupby(day).cumsum().replace(0, np.nan)
    if pd.isna(vwap.iloc[-1]): return "NONE"
    return "LONG" if float(df["close"].iloc[-1]) > float(vwap.iloc[-1]) else "SHORT"


# ── 6-koşullu skor: 4 orijinal (calc_entry) + squeeze + vwap ──
def candidate_score(entry: dict, df1h: pd.DataFrame, d: str):
    sq = squeeze_dir(df1h)
    vw = vwap_dir(df1h)
    if d == "LONG":
        conds = [entry["stoch_long"], entry["rsi_long"], entry["vol_ok"],
                 entry["st_long"], sq == "LONG", vw == "LONG"]
        trigger = (sq == "LONG") or entry["stoch_long"]
    else:
        conds = [entry["stoch_short"], entry["rsi_short"], entry["vol_ok"],
                 entry["st_short"], sq == "SHORT", vw == "SHORT"]
        trigger = (sq == "SHORT") or entry["stoch_short"]
    return sum(bool(x) for x in conds), trigger


def collect_candidate(sym, df1h, df4h, df1d, btc1h):
    entries = []
    n = len(df1h); j_free = 0
    cache = {"n4": -1, "n1d": -1, "trend": None, "daily": None}
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
        # AYNI risk gate'leri (baseline get_signal ile birebir)
        if d == "NONE" or not trend["adx_ok"]:
            continue
        if cfg.get("adx_max") and trend["adx"] >= cfg["adx_max"]:
            continue
        if daily != "NONE" and daily != d:
            continue
        d1 = df1h.iloc[max(0, i - bt.BT_WINDOW): i + 1]
        if len(d1) < max(SQZ_LEN, cfg["stoch_period"]) + 5:
            continue
        try:
            entry = tb.calc_entry(d1.copy())
            if entry is None:
                continue
        except Exception:
            continue
        score, trigger = candidate_score(entry, d1.copy(), d)
        if not trigger:                # tetik yoksa girme (baseline mantığı)
            continue
        if score >= 3:                 # min 3 topla; raporda 4/5 süzülür
            price = float(d1["close"].iloc[-1])
            entries.append({"sym": sym.split("/")[0], "i": i, "side": d,
                            "price": price, "atr": entry["atr"], "score": score,
                            "half": 0 if i < n // 2 else 1})
            j_free = i + max(1, int(cfg["max_pos_hours"])) + 1
    return entries


def sim(entries, dfmap):
    out = []
    for e in entries:
        res = bt.simulate_position(dfmap[e["sym"]], e["i"], e["side"], e["price"], e["atr"])
        if res is None:
            continue
        net, reason, _ = res
        out.append({**e, "net": net, "reason": reason})
    return out


def pf(trades):
    if not trades: return None
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
    log.info("📊 ADAY (6-koşul): stoch+rsi+vol+st + Squeeze + VWAP")
    ex = bt.connect()
    dfmap, meta, btc1h = bt.load_data(ex)
    all_e = []
    for sym, (df1h, df4h, df1d) in meta.items():
        e = collect_candidate(sym, df1h, df4h, df1d, btc1h)
        log.info(f"   [{sym.split('/')[0]:8}] {len(e)} sinyal (min 3)")
        all_e.extend(e)
    trades = sim(all_e, dfmap)
    log.info("\n" + "═" * 74)
    log.info(f"  ADAY 6-koşul  ({len(bt.BT_SYMBOLS)} coin, {bt.BT_1H_LIMIT} saat)  hedef: baseline PF ~1.40")
    log.info("═" * 74)
    line("min 3", trades)
    line("min 4  ← senin öneri", [t for t in trades if t["score"] >= 4])
    line("min 5", [t for t in trades if t["score"] >= 5])
    log.info("  ── İki-yarı robustluk (min 4) ──")
    line("1. yarı", [t for t in trades if t["half"] == 0 and t["score"] >= 4])
    line("2. yarı", [t for t in trades if t["half"] == 1 and t["score"] >= 4])
    log.info("═" * 74)
    log.info("  Karar: min 4 PF baseline 1.40'ı NET geçiyor (≥1.55) VE iki yarı da")
    log.info("         tutuyorsa → aday iyi. Değilse mevcut 5-koşullu kalsın.")


if __name__ == "__main__":
    main()
