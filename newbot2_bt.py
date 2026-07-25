"""
╔══════════════════════════════════════════════════════════════╗
║  YENİ BOT 2 — MEAN-REVERSION (Connors RSI-2 tabanlı)          ║
╚══════════════════════════════════════════════════════════════╝

Neden bu: trend/kırılım stratejileri bu coinlerde doğrandı (coinler mean-reverting).
Dünyada YÜKSEK WR'li dokümante stratejiler mean-reversion ailesidir:
  • Connors RSI-2 (hisse: ~%75 WR): fiyat 200-EMA üstünde + RSI(2)<10 → AL,
    RSI(2)>65 → çık. (Connors sabit stop KULLANMAZ; biz kaldıraçlı futures için
    zorunlu bir GENİŞ felaket-stopu ekliyoruz — aksi halde likidasyon riski.)
  • Bollinger reversion: alt banda değ + RSI<30 → AL. (opsiyonel ek filtre)

DÜRÜST UYARI (baştan): mean-reversion = çok sık KÜÇÜK kazanç + nadir BÜYÜK kayıp.
WR yüksek çıkar ama R:R terstir (~0.6:1). Bu yüzden asıl bakılacak metrik yine
PF'dir — yüksek WR tek başına kâr GARANTİSİ DEĞİL. Rapor R:R'yi de gösterir.

İki evrende test: LİKİT + VOLATİL (mean-reversion volatil/range coinde daha iyi olabilir).
Karar: PF ≥ 1.30 + iki-yarı robust → devam. Değilse revize.

Çalıştırma:  python newbot2_bt.py   (Binance erişimi olan makinede)
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb
import bt_fair
import newbot_bt

cfg = tb.CONFIG
log = tb.log

LEV        = 5
RSI_LEN    = 2
RSI_BUY    = 10        # LONG: RSI(2) bunun altında (aşırı dip)
RSI_EXIT_L = 65        # LONG çıkış: RSI(2) bunun üstünde
RSI_SELL   = 90        # SHORT: RSI(2) bunun üstünde
RSI_EXIT_S = 35
EMA_REG    = 200       # rejim filtresi
ATR_STOP   = 3.0       # GENİŞ felaket-stopu (nadir tetiklensin → WR korunsun)
MAX_HOLD   = 24
MIN_HIST   = 260
COST_FR    = None


def indicators(df):
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, RSI_LEN).rsi()
    ema  = tb.ta.trend.EMAIndicator(c, EMA_REG).ema_indicator()
    atr  = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    return rsi2, ema, atr


def simulate(df, i, side, rsi2, atr_val):
    lev = LEV; cost = COST_FR * 2 * 100 * lev
    entry = float(df["close"].iloc[i]); n = len(df)
    if side == "LONG":
        sl = entry - ATR_STOP * atr_val
    else:
        sl = entry + ATR_STOP * atr_val
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= n:
            j = n - 1; break
        hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j])
        r = rsi2.iloc[j]
        if side == "LONG":
            if lo <= sl:
                return (sl/entry - 1)*100*lev - cost, "STOP", k
            if not np.isnan(r) and r > RSI_EXIT_L:
                px = float(df["close"].iloc[j])
                return (px/entry - 1)*100*lev - cost, "RSI_EXIT", k
        else:
            if hi >= sl:
                return (entry/sl - 1)*100*lev - cost, "STOP", k
            if not np.isnan(r) and r < RSI_EXIT_S:
                px = float(df["close"].iloc[j])
                return (entry/px - 1)*100*lev - cost, "RSI_EXIT", k
    px = float(df["close"].iloc[min(n-1, i+MAX_HOLD)])
    roi = (px/entry - 1)*100*lev if side == "LONG" else (entry/px - 1)*100*lev
    return roi - cost, "TIME", k


def run_symbol(ex, sym):
    try:
        df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
    except Exception as e:
        log.warning(f"   [{sym}] veri hatası: {e}"); return []
    if len(df) < MIN_HIST:
        return []
    rsi2, ema, atr = indicators(df)
    trades = []; j_free = 0; half = len(df) // 2
    for i in range(EMA_REG + 2, len(df) - 1):
        if i < j_free:
            continue
        r = rsi2.iloc[i]; e = ema.iloc[i]; c = float(df["close"].iloc[i]); av = atr.iloc[i]
        if any(np.isnan(x) for x in (r, e, av)):
            continue
        side = None
        if c > e and r < RSI_BUY:      side = "LONG"     # uptrendde aşırı dip → AL
        elif c < e and r > RSI_SELL:   side = "SHORT"    # downtrendde aşırı tepe → SAT
        if side is None:
            continue
        res = simulate(df, i, side, rsi2, float(av))
        if res is None:
            continue
        net, reason, bars = res
        trades.append({"net": net, "reason": reason, "side": side,
                       "half": 0 if i < half else 1})
        j_free = i + bars + 1
    return trades


def stats(trades):
    if not trades:
        return None
    from collections import Counter
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    aw = (gw/len(w) if w else 0); al = (-gl/len(l) if l else 0)
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades),
            "aw": aw, "al": al, "rr": (aw/abs(al) if al else 0),
            "reasons": Counter(t["reason"] for t in trades)}


def report(name, trades):
    s = stats(trades)
    if not s:
        log.info(f"  {name}: işlem yok"); return None
    log.info(f"  {name}:  n={s['n']}  WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  "
             f"net={s['net']:+.1f}%  R:R={s['rr']:.2f} (ort+{s['aw']:.1f}/ort{s['al']:.1f})")
    log.info(f"     çıkışlar: {dict(s['reasons'])}")
    return s


def run_universe(ex, name, symbols):
    allt = []
    for sym in symbols:
        tr = run_symbol(ex, sym)
        allt.extend(tr)
    log.info("\n" + "─" * 62)
    log.info(f"  📦 EVREN: {name}  ({len(symbols)} coin)")
    s = report("TÜMÜ", allt)
    if allt:
        log.info("  ── iki-yarı robustluk ──")
        report("1. yarı", [t for t in allt if t["half"] == 0])
        report("2. yarı", [t for t in allt if t["half"] == 1])
    return s


def main():
    global COST_FR
    COST_FR = cfg["commission"] + cfg["slippage"]
    log.info("📊 YENİ BOT 2 — MEAN-REVERSION (Connors RSI-2) backtest")
    log.info("   RSI(2)<10 + 200EMA üstü → AL | RSI(2)>65 → çık | geniş ATR felaket-stop")
    ex = bt.connect()
    sL = run_universe(ex, "LİKİT", newbot_bt.LIQUID)
    sV = run_universe(ex, "VOLATİL (sabit, yanlılıksız)", bt_fair.FIXED_VOLATILE)
    log.info("\n" + "═" * 62)
    log.info("  🎯 SONUÇ  (hedef PF ≥ 1.30)")
    log.info("═" * 62)
    for nm, s in [("LİKİT", sL), ("VOLATİL", sV)]:
        if s:
            verdict = "✅" if s["pf"] >= 1.30 else "⚪" if s["pf"] >= 1.0 else "❌"
            log.info(f"  {verdict} {nm:8}: PF={s['pf']:.2f}  WR=%{s['wr']:.1f}  net={s['net']:+.1f}%  R:R={s['rr']:.2f}")
    log.info("  Not: yüksek WR + düşük R:R normaldir. KÂR kararı PF'e göre verilir.")
    log.info("═" * 62)


if __name__ == "__main__":
    main()
