"""
OUT-OF-SAMPLE doğrulama — overfitting kontrolü (TEK DOSYA, bağımsız).

Sweep FIXED_VOLATILE'da en iyi varyantı buldu:
    RSI(2)<3  +  Bollinger alt-band  +  ATRstop 3.0   → PF 2.72 (ama n=103, şüpheli)

Bu ayar o veriye FIT edildi. Gerçek mi? DONDUR, hiç görmediği coinlerde çalıştır.
Tutarsa edge gerçek; çökerse overfitting'di. Motor bu dosyada gömülü — dış import yok.

Çalıştırma: python newbot2_oos.py
"""
import numpy as np
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

# ── DONMUŞ kazanan ayar (sweep'te seçildi — DEĞİŞMEZ) ──
RSI_BUY, BB_ON, ATR_STOP = 3, True, 3.0
RSI_EXIT_L, RSI_EXIT_S = 65, 35
EMA_REG, MAX_HOLD, MIN_HIST, LEV = 200, 24, 260, 5
COST_FR = cfg["commission"] + cfg["slippage"]

# Sweep'te OLMAYAN farklı volatil coinler (asıl OOS testi)
OOS_VOLATILE = [f"{b}/USDT:USDT" for b in [
    "FLOKI", "1000SHIB", "PENDLE", "ENS", "ONDO", "ETHFI", "STRK", "W",
    "MANTA", "JASMY", "GRT", "SAND", "MANA", "CHZ", "AXS", "APE", "GMX",
    "COMP", "SNX", "MKR", "EGLD", "FLOW", "CFX", "KAVA", "ROSE", "ALGO",
    "EOS", "HBAR",
]]
# İkinci kontrol: likit evren (tamamen farklı karakter)
LIQUID = [f"{b}/USDT:USDT" for b in [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "TRX", "NEAR", "APT", "ARB", "OP", "INJ", "SUI", "FIL", "ATOM",
    "UNI", "AAVE", "SEI", "TIA", "RUNE",
]]


def simulate(df, i, side, rsi2, atr_val):
    cost = COST_FR * 2 * 100 * LEV
    entry = float(df["close"].iloc[i]); n = len(df)
    sl = entry - ATR_STOP * atr_val if side == "LONG" else entry + ATR_STOP * atr_val
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= n:
            j = n - 1; break
        hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j]); r = rsi2.iloc[j]
        if side == "LONG":
            if lo <= sl:  return (sl/entry-1)*100*LEV - cost, k
            if not np.isnan(r) and r > RSI_EXIT_L:
                return (float(df["close"].iloc[j])/entry-1)*100*LEV - cost, k
        else:
            if hi >= sl:  return (entry/sl-1)*100*LEV - cost, k
            if not np.isnan(r) and r < RSI_EXIT_S:
                return (entry/float(df["close"].iloc[j])-1)*100*LEV - cost, k
    px = float(df["close"].iloc[min(n-1, i+MAX_HOLD)])
    roi = (px/entry-1)*100*LEV if side == "LONG" else (entry/px-1)*100*LEV
    return roi - cost, k


def run_symbol(df):
    rsi_sell = 100 - RSI_BUY
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, 2).rsi()
    ema = tb.ta.trend.EMAIndicator(c, EMA_REG).ema_indicator()
    atr = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    bb = tb.ta.volatility.BollingerBands(c, 20, 2)
    lo_bb, up_bb = bb.bollinger_lband(), bb.bollinger_hband()
    trades = []; j_free = 0; half = len(df) // 2
    for i in range(EMA_REG + 2, len(df) - 1):
        if i < j_free:
            continue
        r = rsi2.iloc[i]; e = ema.iloc[i]; cl = float(c.iloc[i]); av = atr.iloc[i]
        if any(np.isnan(x) for x in (r, e, av)):
            continue
        side = None
        if cl > e and r < RSI_BUY and not np.isnan(lo_bb.iloc[i]) and cl < lo_bb.iloc[i]:
            side = "LONG"
        elif cl < e and r > rsi_sell and not np.isnan(up_bb.iloc[i]) and cl > up_bb.iloc[i]:
            side = "SHORT"
        if side is None:
            continue
        net, bars = simulate(df, i, side, rsi2, float(av))
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


def run_universe(ex, name, symbols):
    allt = []; loaded = 0
    for sym in symbols:
        try:
            df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
        except Exception:
            continue
        if len(df) < MIN_HIST:
            continue
        loaded += 1
        allt.extend(run_symbol(df))
    s = pf_of(allt)
    log.info("\n" + "─" * 60)
    log.info(f"  📦 {name}  ({loaded} coin yüklendi)")
    if not s:
        log.info("     işlem yok"); return None
    s1 = pf_of([t for t in allt if t["half"] == 0])
    s2 = pf_of([t for t in allt if t["half"] == 1])
    p1 = s1["pf"] if s1 else 0; p2 = s2["pf"] if s2 else 0
    log.info(f"     n={s['n']}  WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  net={s['net']:+.1f}%")
    log.info(f"     1.yarı PF={p1:.2f}   2.yarı PF={p2:.2f}")
    return s, p1, p2


def main():
    log.info("📊 OUT-OF-SAMPLE doğrulama — DONMUŞ: RSI<3 + BB + stop3.0")
    log.info("   (bu ayar FIXED_VOLATILE'da seçildi; şimdi GÖRMEDİĞİ coinlerde test)")
    ex = bt.connect()
    rV = run_universe(ex, "OOS_VOLATILE (yeni coinler — ASIL TEST)", OOS_VOLATILE)
    rL = run_universe(ex, "LİKİT (ikinci kontrol)", LIQUID)
    log.info("\n" + "═" * 60)
    log.info("  🎯 OUT-OF-SAMPLE KARARI")
    log.info("═" * 60)
    if rV:
        s, p1, p2 = rV
        if s["pf"] >= 1.30 and p1 >= 1.0 and p2 >= 1.0 and s["n"] >= 60:
            log.info(f"  ✅ GEÇTİ: OOS volatilde PF {s['pf']:.2f}, iki yarı >1 (n={s['n']}).")
            log.info("     Görmediği veride tuttu → overfitting DEĞİL. Canlı hazırlığı konuşulur.")
        elif s["pf"] >= 1.15 and s["n"] >= 60:
            log.info(f"  ⚪ ZAYIF: PF {s['pf']:.2f} (n={s['n']}). Umut var, net değil. Canlıya HENÜZ geçme.")
        else:
            log.info(f"  ❌ ÇÖKTÜ: OOS volatilde PF {s['pf']:.2f} (n={s['n']}).")
            log.info("     2.72 overfitting'di — görmediği veride tutmadı. Canlıya GEÇME.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
