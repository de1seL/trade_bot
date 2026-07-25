"""
YENİ BOT 2 — RAFİNE (dokümante Connors refinementları) + ROBUSTLUK sweep'i.

newbot2 volatil evrende PF 1.03 verdi (pozitif ama zayıf, 2. yarı çöktü). Bu dosya
Connors'ın KENDİ valide ettiği iyileştirmeleri dener — rastgele tuning DEĞİL:
  • RSI(2) eşiği: 10 vs 5 vs 3   (daha ekstrem dip = daha kaliteli reversion)
  • Bollinger alt-band filtresi: kapalı vs açık (sadece en derin dipler)
  • Felaket-stop: 3.0 vs 2.5 vs 2.0 ATR

Her varyant için: TÜMÜ / 1.yarı / 2.yarı PF ayrı gösterilir. KARAR = en yüksek PF
DEĞİL, İKİ YARIDA DA >1 olan (robust) varyant. Aksi = overfit.

Evren: sabit VOLATİL (umut orada). Çalıştırma: python newbot2b_bt.py
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb
import bt_fair

cfg = tb.CONFIG
log = tb.log

LEV = 5
RSI_EXIT_L, RSI_EXIT_S = 65, 35
RSI_SELL_BASE = 90       # short eşiği = 100 - RSI_BUY simetrik ayarlanır
EMA_REG = 200
MAX_HOLD = 24
MIN_HIST = 260
COST_FR = None


def indicators(df, bb_on):
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, 2).rsi()
    ema = tb.ta.trend.EMAIndicator(c, EMA_REG).ema_indicator()
    atr = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    lo_bb = up_bb = None
    if bb_on:
        bb = tb.ta.volatility.BollingerBands(c, 20, 2)
        lo_bb = bb.bollinger_lband(); up_bb = bb.bollinger_hband()
    return rsi2, ema, atr, lo_bb, up_bb


def simulate(df, i, side, rsi2, atr_val, atr_stop):
    lev = LEV; cost = COST_FR * 2 * 100 * lev
    entry = float(df["close"].iloc[i]); n = len(df)
    sl = entry - atr_stop * atr_val if side == "LONG" else entry + atr_stop * atr_val
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= n:
            j = n - 1; break
        hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j]); r = rsi2.iloc[j]
        if side == "LONG":
            if lo <= sl:  return (sl/entry-1)*100*lev - cost, "STOP", k
            if not np.isnan(r) and r > RSI_EXIT_L:
                return (float(df["close"].iloc[j])/entry-1)*100*lev - cost, "RSI_EXIT", k
        else:
            if hi >= sl:  return (entry/sl-1)*100*lev - cost, "STOP", k
            if not np.isnan(r) and r < RSI_EXIT_S:
                return (entry/float(df["close"].iloc[j])-1)*100*lev - cost, "RSI_EXIT", k
    px = float(df["close"].iloc[min(n-1, i+MAX_HOLD)])
    roi = (px/entry-1)*100*lev if side == "LONG" else (entry/px-1)*100*lev
    return roi - cost, "TIME", k


def run_symbol(df, rsi_buy, bb_on, atr_stop):
    rsi_sell = 100 - rsi_buy
    rsi2, ema, atr, lo_bb, up_bb = indicators(df, bb_on)
    trades = []; j_free = 0; half = len(df) // 2
    for i in range(EMA_REG + 2, len(df) - 1):
        if i < j_free:
            continue
        r = rsi2.iloc[i]; e = ema.iloc[i]; c = float(df["close"].iloc[i]); av = atr.iloc[i]
        if any(np.isnan(x) for x in (r, e, av)):
            continue
        side = None
        if c > e and r < rsi_buy:
            if not bb_on or (lo_bb is not None and not np.isnan(lo_bb.iloc[i]) and c < lo_bb.iloc[i]):
                side = "LONG"
        elif c < e and r > rsi_sell:
            if not bb_on or (up_bb is not None and not np.isnan(up_bb.iloc[i]) and c > up_bb.iloc[i]):
                side = "SHORT"
        if side is None:
            continue
        res = simulate(df, i, side, rsi2, float(av), atr_stop)
        net, reason, bars = res
        trades.append({"net": net, "half": 0 if i < half else 1})
        j_free = i + bars + 1
    return trades


def pf_of(trades):
    if not trades:
        return None
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades)}


def main():
    global COST_FR
    COST_FR = cfg["commission"] + cfg["slippage"]
    log.info("📊 YENİ BOT 2 RAFİNE — Connors refinement sweep (volatil evren)")
    log.info("   KARAR: en yüksek PF değil, İKİ YARIDA DA >1 olan varyant (robust)")
    ex = bt.connect()
    # veriyi bir kez çek
    dfs = []
    for sym in bt_fair.FIXED_VOLATILE:
        try:
            df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
            if len(df) >= MIN_HIST:
                dfs.append(df)
        except Exception:
            pass
    log.info(f"   {len(dfs)} coin yüklendi\n")
    log.info(f"  {'RSI<':>4} {'BB':>3} {'ATRstop':>7} | {'n':>4} {'WR%':>5} {'PF':>5} | {'1.yarı PF':>9} {'2.yarı PF':>9} | robust?")
    log.info("  " + "-" * 74)
    results = []
    for rsi_buy in (10, 5, 3):
        for bb_on in (False, True):
            for atr_stop in (3.0, 2.5, 2.0):
                allt = []
                for df in dfs:
                    allt.extend(run_symbol(df, rsi_buy, bb_on, atr_stop))
                s = pf_of(allt)
                if not s or s["n"] < 40:
                    continue
                s1 = pf_of([t for t in allt if t["half"] == 0])
                s2 = pf_of([t for t in allt if t["half"] == 1])
                p1 = s1["pf"] if s1 else 0; p2 = s2["pf"] if s2 else 0
                robust = "✅ EVET" if (p1 >= 1.15 and p2 >= 1.15) else "hayır"
                log.info(f"  {rsi_buy:>4} {str(bb_on):>3} {atr_stop:>7} | {s['n']:>4} {s['wr']:>5.1f} {s['pf']:>5.2f} | "
                         f"{p1:>9.2f} {p2:>9.2f} | {robust}")
                results.append((rsi_buy, bb_on, atr_stop, s, p1, p2))
    log.info("  " + "-" * 74)
    robusts = [r for r in results if r[4] >= 1.15 and r[5] >= 1.15]
    if robusts:
        best = max(robusts, key=lambda r: min(r[4], r[5]))
        log.info(f"  🏆 ROBUST kazanan: RSI<{best[0]} BB={best[1]} ATRstop={best[2]}  "
                 f"→ PF {best[3]['pf']:.2f} (1.yarı {best[4]:.2f} / 2.yarı {best[5]:.2f})")
        log.info("     Bu varyant iki yarıda da tutuyor → ciddiye alınır, canlı hazırlığı konuşulur.")
    else:
        log.info("  ❌ Hiçbir varyant iki yarıda da >1.15 değil. Robust edge YOK.")
        log.info("     Mean-reversion yönü doğru ama bu haliyle güvenilir kâr vermiyor.")
    log.info("═" * 76)


if __name__ == "__main__":
    main()
