"""
╔══════════════════════════════════════════════════════════════╗
║   🤖 trade_bot_2 — DECORRELATED indikatör seti deneyi         ║
╠══════════════════════════════════════════════════════════════╣

Bu dosya trade_bot.py'nin TÜM motorunu aynen kullanır (risk yönetimi,
çıkışlar, dinamik tarayıcı, borsa-SL senkronu, cache, spread guard, günlük
limit... hepsi). SADECE giriş indikatörlerini (calc_entry) değiştirir.

Amaç: indikatörleri "birbiriyle bağlantısız" (decorrelated) yapmak —
her koşul FARKLI bir bilgi kategorisinden gelsin, böylece "X/Y koşul"
gerçekten X bağımsız teyit anlamına gelsin (aynı sinyali tekrar görmek değil).

── İNDİKATÖR SETİ (her biri farklı aileden) ──────────────────────
  1) MACD crossover     → trend-momentum + TETİK
  2) RSI (50 midline)   → osilatör momentum (tek osilatör, StochRSI yok)
  3) Donchian breakout  → VOLATİLİTE/KIRILIM (fiyat son N mum zirvesini kırdı mı)
  4) CMF (Chaikin)      → HACİM/para akışı (gerçek alım/satım baskısı)

  TETİK (≥1 şart): MACD crossover VEYA Donchian breakout (ikisi de taze olay)
  Skor: 4 koşuldan kaçı → get_signal min_conditions ile karşılaştırır

Gating (1d/4h EMA200 + ADX, 1h EMA) trade_bot'taki gibi aynen korunur.

⚠️  "Daha çok kâr" GARANTİSİ YOK — bu sadece daha bağımsız bir set.
    Hangisinin gerçekten iyi olduğunu backtest/dry_run karşılaştırması söyler.

Çalıştırma:  python trade_bot_2.py
"""

import pandas as pd
import ta

import trade_bot as tb

CONFIG = tb.CONFIG
log    = tb.log

# ── v2'ye özel parametreler ──────────────────────────────────────
DONCHIAN_PERIOD = 20     # kaç mumun zirvesi/dibi kırılımı sayılsın
CMF_PERIOD      = 20
RSI_MID         = 50     # trend momentum eşiği (osilatör)

# Decorrelated set daha seçici (her koşul bağımsız), bu yüzden eşiği biraz düşür.
CONFIG["min_conditions"] = 2     # 4 bağımsız koşuldan en az 2 + zorunlu tetik

# Bu bir DENEY botu → DRY RUN (kağıt üzerinde, gerçek emir YOK, para riski YOK).
# Ayrı process olduğu için trade_bot.py'yi ETKİLEMEZ; o kendi ayarıyla çalışır.
CONFIG["dry_run"] = True


def calc_entry_v2(df: pd.DataFrame) -> dict | None:
    """trade_bot.calc_entry'nin DECORRELATED karşılığı. get_signal/log_scan'in
    beklediği sözleşme anahtarlarını döner: long_score/short_score/
    long_trigger/short_trigger/price/atr/coin_chg_1h."""
    cfg = CONFIG
    c   = df["close"]

    # 1) MACD (trend-momentum + tetik)
    macd_obj    = ta.trend.MACD(c, window_slow=cfg["macd_slow"],
                                window_fast=cfg["macd_fast"], window_sign=cfg["macd_sig"])
    df["macd"]  = macd_obj.macd()
    df["msig"]  = macd_obj.macd_signal()

    # 2) RSI (osilatör momentum)
    df["rsi"]   = ta.momentum.RSIIndicator(c, window=cfg["rsi_period"]).rsi()

    # 3) Donchian breakout (volatilite/kırılım) — ÖNCEKİ N mumun zirvesi/dibi
    df["dc_up"] = df["high"].rolling(DONCHIAN_PERIOD).max().shift(1)
    df["dc_dn"] = df["low"].rolling(DONCHIAN_PERIOD).min().shift(1)

    # 4) CMF (hacim/para akışı)
    df["cmf"]   = ta.volume.ChaikinMoneyFlowIndicator(
        df["high"], df["low"], c, df["volume"], window=CMF_PERIOD
    ).chaikin_money_flow()

    # ATR (SL/TP için — trade_bot ile aynı)
    df["atr"]   = ta.volatility.AverageTrueRange(
        df["high"], df["low"], c, window=cfg["atr_period"]
    ).average_true_range()

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    price = float(last["close"])
    coin_chg_1h = (price - float(prev["close"])) / float(prev["close"])

    # NaN koruması
    for col in ["macd", "msig", "rsi", "dc_up", "dc_dn", "cmf", "atr"]:
        if pd.isna(last[col]):
            return None

    # MACD crossover (son macd_lookback mumda)
    lb  = cfg["macd_lookback"]
    win = df.tail(lb + 1)
    macd_up = macd_down = False
    for i in range(len(win) - 1):
        p = win.iloc[i]; cc = win.iloc[i + 1]
        if p["macd"] <= p["msig"] and cc["macd"] > cc["msig"]:
            macd_up = True
        if p["macd"] >= p["msig"] and cc["macd"] < cc["msig"]:
            macd_down = True

    # RSI momentum (50 üstü/altı + yön)
    rsi_val    = float(last["rsi"])
    rsi_series = df["rsi"].dropna()
    rsi_rising  = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) > float(rsi_series.iloc[-3])
    rsi_falling = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) < float(rsi_series.iloc[-3])
    rsi_long   = rsi_val > RSI_MID and rsi_rising
    rsi_short  = rsi_val < RSI_MID and rsi_falling

    # Donchian breakout
    donch_long  = price > float(last["dc_up"])
    donch_short = price < float(last["dc_dn"])

    # CMF (para akışı yönü)
    cmf_val   = float(last["cmf"])
    cmf_long  = cmf_val > 0
    cmf_short = cmf_val < 0

    # Skor (4 bağımsız koşul) + tetik (taze olay)
    long_score  = sum([macd_up,   rsi_long,  donch_long,  cmf_long])
    short_score = sum([macd_down, rsi_short, donch_short, cmf_short])
    long_trigger  = macd_up   or donch_long
    short_trigger = macd_down or donch_short

    return {
        "price"       : round(price, 6),
        "atr"         : round(float(last["atr"]), 6),
        "coin_chg_1h" : round(coin_chg_1h, 4),
        "rsi"         : round(rsi_val, 1),
        "macd"        : round(float(last["macd"]), 6),
        "msig"        : round(float(last["msig"]), 6),
        "cmf"         : round(cmf_val, 3),
        "dc_up"       : round(float(last["dc_up"]), 6),
        "dc_dn"       : round(float(last["dc_dn"]), 6),
        "macd_up"     : macd_up,
        "macd_down"   : macd_down,
        "rsi_long"    : rsi_long,
        "rsi_short"   : rsi_short,
        "donch_long"  : donch_long,
        "donch_short" : donch_short,
        "cmf_long"    : cmf_long,
        "cmf_short"   : cmf_short,
        "long_score"  : long_score,
        "short_score" : short_score,
        "long_trigger"  : long_trigger,
        "short_trigger" : short_trigger,
    }


def log_scan_v2(sym, trend, entry, signal, pos, daily, trend_1h="NONE"):
    """v2 indikatör kümesi için tarama logu."""
    t   = lambda b: "✅" if b else "⬜"
    cfg = CONFIG

    trail_info = ""
    if pos.active:
        if pos.side == "LONG":
            pnl = (entry["price"] / pos.entry_price - 1) * 100 * cfg["leverage"]
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Peak: {pos.peak:,.6f})  PnL: {pnl:+.2f}%"
        else:
            pnl = (pos.entry_price / entry["price"] - 1) * 100 * cfg["leverage"]
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Valley: {pos.valley:,.6f})  PnL: {pnl:+.2f}%"

    daily_ok = daily == "NONE" or daily == trend["direction"]

    log.info(
        f"\n{'─'*54}\n"
        f"  [{sym}]  (v2 decorrelated)\n"
        f"  1d: {'✅' if daily_ok else '⬜'} {daily}  "
        f"4h: {'📈' if trend['direction']=='LONG' else '📉' if trend['direction']=='SHORT' else '➡'} {trend['direction']}  "
        f"1h: {trend_1h}\n"
        f"  ADX  : {trend['adx']:.1f}  {'✅' if trend['adx_ok'] else '⬜ yatay'}\n"
        f"  Fiyat: {entry['price']:,.6f}   ATR: {entry['atr']:,.6f}\n"
        f"  RSI:{entry['rsi']:.1f}  MACD:{entry['macd']:.5f}/{entry['msig']:.5f}  CMF:{entry['cmf']:+.3f}\n"
        f"  Donchian: üst={entry['dc_up']:,.6f}  alt={entry['dc_dn']:,.6f}\n"
        f"  LONG ({entry['long_score']}/4, min={cfg['min_conditions']}): "
        f"MACD{t(entry['macd_up'])} RSI{t(entry['rsi_long'])} Kırılım{t(entry['donch_long'])} CMF{t(entry['cmf_long'])}\n"
        f"  SHORT({entry['short_score']}/4, min={cfg['min_conditions']}): "
        f"MACD{t(entry['macd_down'])} RSI{t(entry['rsi_short'])} Kırılım{t(entry['donch_short'])} CMF{t(entry['cmf_short'])}\n"
        f"  Sinyal: {signal}   Pozisyon: {pos.side if pos.active else 'YOK'}"
        f"{trail_info}\n"
        f"{'─'*54}"
    )


# ── Motoru trade_bot'tan al, SADECE indikatör beynini değiştir ───
# run_symbol/main trade_bot içinde global 'calc_entry' ve 'log_scan' adlarını
# çağırır; bunları v2 sürümleriyle değiştiriyoruz. Geri kalan her şey aynı.
tb.calc_entry = calc_entry_v2
tb.log_scan   = log_scan_v2


def main():
    log.info("🧪 trade_bot_2 — DECORRELATED set (MACD + RSI + Donchian + CMF)")
    tb.main()


if __name__ == "__main__":
    main()
