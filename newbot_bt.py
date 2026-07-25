"""
╔══════════════════════════════════════════════════════════════╗
║  YENİ BOT — "Pullback Trend"  (sıfırdan, KANITA dayalı tasarım)║
╚══════════════════════════════════════════════════════════════╝

Bu tasarım, aylarca yaptığımız testlerin ÖĞRETTİKLERİ üzerine kurulu — rastgele
indikatör kombinasyonu DEĞİL:

  1) Evren = LİKİT coinler (edge orada: majörlerde PF 1.40, volatil memede 0.65).
  2) Sadece REJİMLE aynı yön (4h trend) — trendle savaşma.
  3) GİRİŞ = pullback (trendde geri çekilmeyi al), kırılım/tepe DEĞİL.
  4) Sabit 2:1 R:R — risk 1R, hedef 2R. %40 WR bile kârlı: 0.4*2 - 0.6*1 = +0.2/işlem.
  5) ATR-tabanlı sıkı stop + +1R'de başabaş. Kısmi yok (R:R'yi bozmaz).
  6) 5x kaldıraç (varyansı yarıya indir).

İNDİKATÖRLER (minimal, sağlam):
  4h: EMA20/50/200 (rejim)      1h: EMA20 (pullback), RSI14, MACD hist, ATR14

Bu SADECE backtest — kural kanıtlanırsa canlı botu bunun ETRAFINA kurarız.
Karar eşiği: likit evrende PF ≥ 1.30 VE iki-yarı robust → devam. Değilse tasarımı
revize ederiz (canlıya geçmeden).

Çalıştırma:  python newbot_bt.py   (Binance erişimi olan makinede)
API anahtarı GEREKMEZ, emir YOK, sadece geçmiş veri.
"""
import numpy as np
import pandas as pd
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

# ── Parametreler (hepsi tek yerde, sweep kolay) ──
LEV        = 5
ATR_MULT   = 1.2       # stop mesafesi = ATR_MULT * ATR
TP_R       = 2.0       # hedef = TP_R * risk (2:1)
BE_R       = 1.0       # +BE_R R'de stop başabaşa
PULLBACK_LB= 4         # son kaç barda EMA20'ye geri çekilme aranır
RSI_MAX    = 68        # LONG'da aşırı-alımı kovalama (SHORT'ta 100-RSI_MAX)
MAX_HOLD   = 48        # bar (saat) tutuş tavanı
MIN_HIST   = 260
COST_FR    = None      # aşağıda cfg'den

# LİKİT EVREN — edge'in olduğu yer (top hacim, meme değil)
LIQUID = [f"{b}/USDT:USDT" for b in [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "TRX", "NEAR", "APT", "ARB", "OP", "INJ", "SUI", "FIL", "ATOM",
    "UNI", "AAVE", "SEI", "TIA", "RUNE",
]]


def ind_4h(df4):
    c = df4["close"]
    e20 = tb.ta.trend.EMAIndicator(c, 20).ema_indicator()
    e50 = tb.ta.trend.EMAIndicator(c, 50).ema_indicator()
    e200= tb.ta.trend.EMAIndicator(c, 200).ema_indicator()
    return e20, e50, e200


def regime(e20, e50, e200, price):
    if np.isnan(e200) or np.isnan(e50):
        return "FLAT"
    if e20 > e50 and price > e200:
        return "UP"
    if e20 < e50 and price < e200:
        return "DOWN"
    return "FLAT"


def ind_1h(df):
    c = df["close"]
    ema20 = tb.ta.trend.EMAIndicator(c, 20).ema_indicator()
    rsi   = tb.ta.momentum.RSIIndicator(c, 14).rsi()
    macd  = tb.ta.trend.MACD(c).macd_diff()          # histogram
    atr   = tb.ta.volatility.AverageTrueRange(df["high"], df["low"], c, 14).average_true_range()
    return ema20, rsi, macd, atr


def entry_signal(df, i, ema20, rsi, macd, reg):
    """i. barda pullback girişi var mı? reg = 4h rejim (UP/DOWN)."""
    if reg == "FLAT":
        return None
    e = ema20.iloc[i]; r = rsi.iloc[i]; rp = rsi.iloc[i-1]
    m = macd.iloc[i]; mp = macd.iloc[i-1]
    close = df["close"].iloc[i]
    if any(np.isnan(x) for x in (e, r, rp, m, mp)):
        return None
    lows  = df["low"].iloc[i-PULLBACK_LB:i+1]
    highs = df["high"].iloc[i-PULLBACK_LB:i+1]
    if reg == "UP":
        pulled = (lows <= ema20.iloc[i-PULLBACK_LB:i+1]).any()   # EMA20'ye değdi
        reclaim = close > e                                       # geri aldı
        mom = (r > rp) and (m > mp) and (r < RSI_MAX)             # toparlıyor, aşırı değil
        if pulled and reclaim and mom:
            return "LONG"
    else:
        pushed = (highs >= ema20.iloc[i-PULLBACK_LB:i+1]).any()
        reclaim = close < e
        mom = (r < rp) and (m < mp) and (r > 100 - RSI_MAX)
        if pushed and reclaim and mom:
            return "SHORT"
    return None


def simulate(df, i, side, atr_val):
    lev = LEV
    cost = COST_FR * 2 * 100 * lev
    entry = float(df["close"].iloc[i])
    risk = ATR_MULT * atr_val
    if risk <= 0:
        return None
    if side == "LONG":
        sl = entry - risk; tp = entry + TP_R * risk; be_lvl = entry + BE_R * risk
    else:
        sl = entry + risk; tp = entry - TP_R * risk; be_lvl = entry - BE_R * risk
    n = len(df); moved_be = False
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= n:
            j = n - 1; break
        hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j])
        if side == "LONG":
            if not moved_be and hi >= be_lvl:
                sl = max(sl, entry); moved_be = True
            if lo <= sl:
                px = sl; roi = (px/entry - 1)*100*lev - cost
                return roi, ("BE" if moved_be and sl >= entry else "SL"), k
            if hi >= tp:
                roi = (tp/entry - 1)*100*lev - cost
                return roi, "TP", k
        else:
            if not moved_be and lo <= be_lvl:
                sl = min(sl, entry); moved_be = True
            if hi >= sl:
                px = sl; roi = (entry/px - 1)*100*lev - cost
                return roi, ("BE" if moved_be and sl <= entry else "SL"), k
            if lo <= tp:
                roi = (entry/tp - 1)*100*lev - cost
                return roi, "TP", k
    exit_px = float(df["close"].iloc[j])
    roi = (exit_px/entry - 1)*100*lev if side == "LONG" else (entry/exit_px - 1)*100*lev
    return roi - cost, "TIME", (j - i)


def run_symbol(ex, sym):
    try:
        df1 = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
        df4 = bt.fetch_tf(ex, sym, "4h", bt.BT_4H_LIMIT)
    except Exception as e:
        log.warning(f"   [{sym}] veri hatası: {e}"); return []
    if len(df1) < MIN_HIST:
        return []
    ema20, rsi, macd, atr = ind_1h(df1)
    e20, e50, e200 = ind_4h(df4)
    trades = []; j_free = 0; half_n = len(df1) // 2
    for i in range(PULLBACK_LB + 2, len(df1) - 1):
        if i < j_free:
            continue
        now = df1.index[i] + pd.Timedelta(hours=1)
        d4 = df4[df4.index + pd.Timedelta(hours=4) <= now]
        if len(d4) < 50:
            continue
        li = len(d4) - 1
        reg = regime(e20.iloc[li], e50.iloc[li], e200.iloc[li], float(d4["close"].iloc[-1]))
        sig = entry_signal(df1, i, ema20, rsi, macd, reg)
        if sig is None:
            continue
        av = atr.iloc[i]
        if np.isnan(av):
            continue
        res = simulate(df1, i, sig, float(av))
        if res is None:
            continue
        net, reason, bars = res
        trades.append({"net": net, "reason": reason, "side": sig,
                       "half": 0 if i < half_n else 1})
        j_free = i + bars + 1
    return trades


def stats(trades):
    if not trades:
        return None
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    from collections import Counter
    return {"n": len(trades), "wr": len(w)/len(trades)*100,
            "pf": (gw/gl if gl > 0 else 99), "net": sum(t["net"] for t in trades),
            "aw": (gw/len(w) if w else 0), "al": (-gl/len(l) if l else 0),
            "reasons": Counter(t["reason"] for t in trades)}


def report(name, trades):
    s = stats(trades)
    if not s:
        log.info(f"  {name}: işlem yok"); return None
    log.info(f"  {name}:  n={s['n']}  WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  "
             f"net={s['net']:+.1f}%  ort+={s['aw']:+.1f}  ort-={s['al']:+.1f}")
    log.info(f"     çıkışlar: {dict(s['reasons'])}")
    return s


def main():
    global COST_FR
    COST_FR = cfg["commission"] + cfg["slippage"]
    log.info("📊 YENİ BOT 'Pullback Trend' backtest — likit evren, 2:1 R:R, 5x")
    log.info(f"   {len(LIQUID)} likit coin  |  hedef: PF ≥ 1.30 + iki-yarı robust")
    ex = bt.connect()
    allt = []; per = {}
    for sym in LIQUID:
        tr = run_symbol(ex, sym)
        if tr:
            per[sym.split('/')[0]] = sum(t["net"] for t in tr), len(tr)
            allt.extend(tr)
        log.info(f"   [{sym.split('/')[0]:8}] {len(tr)} işlem")
    log.info("\n" + "═" * 62)
    log.info("  🎯 YENİ BOT SONUCU")
    log.info("═" * 62)
    s = report("TÜMÜ", allt)
    log.info("  ── iki-yarı robustluk ──")
    report("1. yarı", [t for t in allt if t["half"] == 0])
    report("2. yarı", [t for t in allt if t["half"] == 1])
    if per:
        log.info("  ── coin bazında net (kötüden iyiye) ──")
        for c, (v, cnt) in sorted(per.items(), key=lambda x: x[1][0]):
            log.info(f"     {c:8} {v:>+7.1f}%  ({cnt})")
    if s:
        log.info("═" * 62)
        if s["pf"] >= 1.30:
            log.info(f"  ✅ PF {s['pf']:.2f} ≥ 1.30 — söz verdiğim eşik. İki yarı da tutuyorsa canlıya hazırlarız.")
        elif s["pf"] >= 1.0:
            log.info(f"  ⚪ PF {s['pf']:.2f} — pozitif ama zayıf. Parametre sweep'i deneriz.")
        else:
            log.info(f"  ❌ PF {s['pf']:.2f} < 1.0 — bu tasarım da tutmadı, revize ederiz (canlıya GEÇME).")
    log.info("═" * 62)


if __name__ == "__main__":
    main()
