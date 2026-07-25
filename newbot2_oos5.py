"""
OOS karşılaştırma: RSI<3 vs RSI<5 (ikisi de BB + stop3.0) — görmediği coinlerde.

Amaç: RSI<5 daha çok işlem verirken edge'i (PF ~1.27) koruyor mu? Eğer OOS'ta da
tutuyorsa → daha çok işlem + aynı WR (kullanıcının istediği). Tutmuyorsa RSI<3 kalır.

Tek dosya, bağımsız. Çalıştırma: python newbot2_oos5.py
"""
import numpy as np
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

RSI_EXIT_L, RSI_EXIT_S = 65, 35
EMA_REG, MAX_HOLD, MIN_HIST, LEV, ATR_STOP = 200, 24, 260, 5, 3.0
COST_FR = cfg["commission"] + cfg["slippage"]

OOS_VOLATILE = [f"{b}/USDT:USDT" for b in [
    "FLOKI", "1000SHIB", "PENDLE", "ENS", "ONDO", "ETHFI", "STRK", "W",
    "MANTA", "JASMY", "GRT", "SAND", "MANA", "CHZ", "AXS", "APE", "GMX",
    "COMP", "SNX", "MKR", "EGLD", "FLOW", "CFX", "KAVA", "ROSE", "ALGO",
    "EOS", "HBAR",
]]
LIQUID = [f"{b}/USDT:USDT" for b in [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "TRX", "NEAR", "APT", "ARB", "OP", "INJ", "SUI", "FIL", "ATOM",
    "UNI", "AAVE", "SEI", "TIA", "RUNE",
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


def run_symbol(df, rsi_buy):
    rsi_sell = 100 - rsi_buy
    c = df["close"]
    rsi2 = tb.ta.momentum.RSIIndicator(c, 2).rsi()
    ema = tb.ta.trend.EMAIndicator(c, EMA_REG).ema_indicator()
    atr = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    bb = tb.ta.volatility.BollingerBands(c, 20, 2)
    lo_bb, up_bb = bb.bollinger_lband(), bb.bollinger_hband()
    trades = []; j_free = 0; half = len(df)//2
    for i in range(EMA_REG+2, len(df)-1):
        if i < j_free:
            continue
        r = rsi2.iloc[i]; e = ema.iloc[i]; cl = float(c.iloc[i]); av = atr.iloc[i]
        if any(np.isnan(x) for x in (r, e, av)):
            continue
        side = None
        if cl > e and r < rsi_buy and not np.isnan(lo_bb.iloc[i]) and cl < lo_bb.iloc[i]:
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
    w = [t["net"] for t in trades if t["net"] > 0]; l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades)}


def evaluate(dfs, rsi_buy):
    allt = []
    for df in dfs:
        allt.extend(run_symbol(df, rsi_buy))
    s = pf_of(allt)
    if not s:
        return None
    s1 = pf_of([t for t in allt if t["half"] == 0]); s2 = pf_of([t for t in allt if t["half"] == 1])
    return s, (s1["pf"] if s1 else 0), (s2["pf"] if s2 else 0)


def main():
    log.info("📊 OOS: RSI<3 vs RSI<5 (BB + stop3.0) — görmediği coinlerde")
    ex = bt.connect()
    for uname, syms in [("OOS_VOLATILE (asıl test)", OOS_VOLATILE), ("LİKİT", LIQUID)]:
        dfs = []
        for sym in syms:
            try:
                df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
                if len(df) >= MIN_HIST:
                    dfs.append(df)
            except Exception:
                pass
        log.info("\n" + "═" * 60)
        log.info(f"  📦 {uname}  ({len(dfs)} coin)")
        log.info(f"  {'eşik':>6} | {'n':>4} {'WR%':>5} {'PF':>5} {'net%':>8} | {'1.yarı':>6} {'2.yarı':>6}")
        log.info("  " + "-" * 52)
        for rsi_buy in (3, 5):
            r = evaluate(dfs, rsi_buy)
            if not r:
                log.info(f"  RSI<{rsi_buy}: işlem yok"); continue
            s, p1, p2 = r
            log.info(f"  RSI<{rsi_buy:>2} | {s['n']:>4} {s['wr']:>5.1f} {s['pf']:>5.2f} {s['net']:>+8.1f} | {p1:>6.2f} {p2:>6.2f}")
    log.info("\n" + "═" * 60)
    log.info("  Yorum: RSI<5, RSI<3'e yakın PF + iki yarı >1 verirken DAHA ÇOK n")
    log.info("         veriyorsa → mr_bot'u RSI<5'e çevir (işlem↑, edge sabit). Değilse RSI<3 kalsın.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
