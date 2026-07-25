"""
MACD hipotez testi — backtest.py makinesini kullanır ama her girişin MACD
koşulunu (macd_up/macd_down, yön-uygun) kaydeder, sonucu MACD=True vs False
olarak ayırır. CSV'de bulduğumuz "MACD tutan girişler daha kötü" bulgusunu
geçmiş veride (12+ coin, ~1000 saatlik mum) doğrular/çürütür.

Ek olarak score kırılımını da verir (dönemler arası tutarlı mı diye).
"""
import backtest as bt
import trade_bot as tb
import pandas as pd
from collections import defaultdict

cfg = tb.CONFIG
log = tb.log


def collect_with_macd(sym, df1h, df4h, df1d, btc1h):
    """backtest.collect_entries'in aynısı ama her girişe macd_cond + score ekler."""
    entries = []
    n = len(df1h)
    j_free = 0
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
        d1 = df1h.iloc[max(0, i - bt.BT_WINDOW): i + 1]
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
        if bt.BT_USE_BTC and btc1h is not None:
            b = btc1h[btc1h.index <= df1h.index[i]]
            if len(b) >= 2:
                btc_chg = float(b["close"].iloc[-1]) / float(b["close"].iloc[-2]) - 1
        signal = tb.get_signal(trend, entry, daily, btc_chg, entry_trend, "NONE", "NONE")
        if signal in ("LONG", "SHORT"):
            price = float(d1["close"].iloc[-1])
            macd_cond = entry["macd_up"] if signal == "LONG" else entry["macd_down"]
            score = entry.get("long_score" if signal == "LONG" else "short_score")
            if score is None:  # skor alanı yoksa yeniden say
                if signal == "LONG":
                    score = sum([entry["stoch_long"], entry["rsi_long"], entry["macd_up"], entry["vol_ok"], entry["st_long"]])
                else:
                    score = sum([entry["stoch_short"], entry["rsi_short"], entry["macd_down"], entry["vol_ok"], entry["st_short"]])
            entries.append({"sym": sym.split("/")[0], "i": i, "side": signal,
                            "price": price, "atr": entry["atr"],
                            "macd": bool(macd_cond), "score": int(score)})
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


def pf_line(label, trades):
    if not trades:
        log.info(f"  {label:16} yok")
        return
    n = len(trades)
    w = [t["net"] for t in trades if t["net"] > 0]
    l = [t["net"] for t in trades if t["net"] <= 0]
    gw, gl = sum(w), -sum(l)
    pf = gw / gl if gl > 0 else 99
    log.info(f"  {label:16} n={n:>4}  WR=%{len(w)/n*100:>4.1f}  "
             f"PF={pf:>5.2f}  net={sum(t['net'] for t in trades):>+7.1f}%  "
             f"ort+={(gw/len(w) if w else 0):>+5.1f}  ort-={(-gl/len(l) if l else 0):>+5.1f}")


def main():
    log.info("📊 MACD hipotez testi başlıyor")
    ex = bt.connect()
    dfmap, meta, btc1h = bt.load_data(ex)
    all_e = []
    for sym, (df1h, df4h, df1d) in meta.items():
        e = collect_with_macd(sym, df1h, df4h, df1d, btc1h)
        log.info(f"   [{sym.split('/')[0]:8}] {len(e)} sinyal")
        all_e.extend(e)
    trades = sim(all_e, dfmap)
    log.info("\n" + "═" * 70)
    log.info(f"  TOPLAM {len(trades)} işlem  ({len(bt.BT_SYMBOLS)} coin, {bt.BT_1H_LIMIT} saatlik mum)")
    log.info("═" * 70)
    pf_line("HEPSİ", trades)
    log.info("  ── MACD koşuluna göre ──")
    pf_line("MACD=True", [t for t in trades if t["macd"]])
    pf_line("MACD=False", [t for t in trades if not t["macd"]])
    log.info("  ── Skora göre ──")
    for sc in [3, 4, 5]:
        pf_line(f"score={sc}", [t for t in trades if t["score"] == sc])
    log.info("═" * 70)


if __name__ == "__main__":
    main()
