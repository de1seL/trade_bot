"""
ADX filtresi OOS testi — mean-reversion'a "sadece yatay/testere piyasada işlem aç"
kuralı eklemek edge'i artırıyor mu? (Trend güçlüyken girme → büyük stopları ele.)

Donmuş çekirdek: RSI(2)<5 + Bollinger alt/üst + 200EMA + 3xATR stop + RSI çıkış.
Tek eklenen: ADX(14) kapısı. ADX_MAX=None (kapalı/baseline) vs 35/30/25.
Görmediği coinlerde (OOS_VOLATILE). KARAR: bir ADX kapısı hem PF'yi artırıyor
hem İKİ YARIDA DA >1 tutuyorsa → mantıklı, mr_bot'a eklenir. Değilse eklenmez.

Tek dosya. Çalıştırma: python newbot2_adx.py
"""
import numpy as np
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

RSI_BUY, RSI_SELL = 5, 95
RSI_EXIT_L, RSI_EXIT_S = 65, 35
EMA_REG, MAX_HOLD, MIN_HIST, LEV, ATR_STOP = 200, 24, 260, 5, 3.0
COST_FR = cfg["commission"] + cfg["slippage"]

OOS_VOLATILE = [f"{b}/USDT:USDT" for b in [
    "FLOKI", "1000SHIB", "PENDLE", "ENS", "ONDO", "ETHFI", "STRK", "W",
    "MANTA", "JASMY", "GRT", "SAND", "MANA", "CHZ", "AXS", "APE", "GMX",
    "COMP", "SNX", "MKR", "EGLD", "FLOW", "CFX", "KAVA", "ROSE", "ALGO",
    "EOS", "HBAR",
]]


def simulate(df, i, side, rsi2, atr_val):
    cost = COST_FR * 2 * 100 * LEV
    entry = float(df["close"].iloc[i]); n = len(df)
    sl = entry - ATR_STOP*atr_val if side == "LONG" else entry + ATR_STOP*atr_val
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


def run_symbol(df, adx_max):
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, 2).rsi()
    ema = tb.ta.trend.EMAIndicator(c, EMA_REG).ema_indicator()
    atr = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    adx = tb.ta.trend.ADXIndicator(df["high"], df["low"], c, 14).adx()
    bb = tb.ta.volatility.BollingerBands(c, 20, 2)
    lo_bb, up_bb = bb.bollinger_lband(), bb.bollinger_hband()
    trades = []; j_free = 0; half = len(df)//2
    for i in range(EMA_REG+2, len(df)-1):
        if i < j_free:
            continue
        r = rsi2.iloc[i]; e = ema.iloc[i]; cl = float(c.iloc[i]); av = atr.iloc[i]; ax = adx.iloc[i]
        if any(np.isnan(x) for x in (r, e, av)):
            continue
        if adx_max is not None and (np.isnan(ax) or ax >= adx_max):
            continue                                   # trend çok güçlü → girme
        side = None
        if cl > e and r < RSI_BUY and not np.isnan(lo_bb.iloc[i]) and cl < lo_bb.iloc[i]:
            side = "LONG"
        elif cl < e and r > RSI_SELL and not np.isnan(up_bb.iloc[i]) and cl > up_bb.iloc[i]:
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
    w = [t["net"] for t in trades if t["net"] > 0]; l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades)}


def main():
    log.info("📊 ADX filtresi OOS testi (mean-reversion, görmediği coinler)")
    ex = bt.connect()
    dfs = []
    for sym in OOS_VOLATILE:
        try:
            df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
            if len(df) >= MIN_HIST:
                dfs.append(df)
        except Exception:
            pass
    log.info(f"   {len(dfs)} coin yüklendi\n")
    log.info(f"  {'ADX kapı':>9} | {'n':>4} {'WR%':>5} {'PF':>5} {'net%':>8} | {'1.yarı':>6} {'2.yarı':>6}")
    log.info("  " + "-" * 56)
    for adx_max in (None, 35, 30, 25):
        allt = []
        for df in dfs:
            allt.extend(run_symbol(df, adx_max))
        s = pf_of(allt)
        if not s:
            log.info(f"  {'kapalı' if adx_max is None else '<'+str(adx_max):>9} | işlem yok"); continue
        s1 = pf_of([t for t in allt if t["half"] == 0]); s2 = pf_of([t for t in allt if t["half"] == 1])
        p1 = s1["pf"] if s1 else 0; p2 = s2["pf"] if s2 else 0
        label = "kapalı" if adx_max is None else f"<{adx_max}"
        log.info(f"  {label:>9} | {s['n']:>4} {s['wr']:>5.1f} {s['pf']:>5.2f} {s['net']:>+8.1f} | {p1:>6.2f} {p2:>6.2f}")
    log.info("  " + "-" * 56)
    log.info("  Yorum: bir ADX kapısı 'kapalı'ya göre PF'yi artırıp İKİ YARIYI DA >1")
    log.info("         yapıyorsa → mr_bot'a ekle. n çok düşerse (aşırı filtre) ekleme.")


if __name__ == "__main__":
    main()
