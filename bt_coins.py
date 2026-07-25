"""
COIN SEÇİMİ testi — asıl kök-neden hipotezi.

Hipotez: strateji MAJÖR (likit) coinlerde PF ~1.40 veriyor, ama canlı bot
`top_volatile_count` ile EN VOLATİL (düşük-cap, geniş-spread) coinleri seçiyor
ve edge orada eriyor. Bunu rakamla göster.

Ne yapar:
  • AYNI strateji beynini (baseline) İKİ ayrı coin kovasında çalıştırır:
      A) MAJÖRLER  — likit büyük-cap (backtest baseline listesi)
      B) VOLATİL   — botun canlıda seçtiği tipteki coinler
         (fetch_tickers → skor = |%değişim| × hacim, hacim≥$10M, majör hariç,
          botun get_symbols mantığının aynısı)
  • Her kova için PF/WR/net + coin bazında net (en kötüler görünür).

DÜRÜST sınır: volatil kova "BUGÜN volatil olan" coinlerin GEÇMİŞİni test eder
(hafif ileriye-bakış yanlılığı). Yine de majör-vs-volatil edge farkını gösterir.
Ayrıca kısa geçmişli yeni coinler otomatik atlanır (yeterli mum yoksa).

Çalıştırma:  python bt_coins.py    (Binance erişimi olan makinede)
"""
import pandas as pd
import backtest as bt
import trade_bot as tb

cfg = tb.CONFIG
log = tb.log

MAJORS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT",
    "ADA/USDT:USDT", "DOT/USDT:USDT", "LTC/USDT:USDT", "TRX/USDT:USDT",
]
VOLATILE_N = 15          # botun seçtiği tipten kaç volatil coin test edilsin
STABLE = tb.STABLE


def pick_volatile(ex, n, exclude):
    """Botun get_symbols mantığının aynısı: |%değişim|×hacim skoru, hacim≥$10M,
    majörler hariç → en volatil n coin."""
    markets = ex.load_markets()
    tickers = ex.fetch_tickers()
    exbase  = {s.split("/")[0] for s in exclude}
    valid = {
        m["symbol"] for m in markets.values()
        if m.get("type") == "swap" and m.get("linear") and m.get("active")
        and m.get("quote") == "USDT" and m.get("base") not in STABLE
        and m.get("base") not in exbase
    }
    rows = []
    for sym, t in tickers.items():
        if sym not in valid:
            continue
        vol = t.get("quoteVolume") or 0
        pct = abs(t.get("percentage") or 0)
        if vol < 10_000_000 or pct <= 0:
            continue
        rows.append({"symbol": sym, "pct": pct, "vol_m": vol / 1e6, "score": pct * vol})
    if not rows:
        return []
    df = pd.DataFrame(rows).sort_values("score", ascending=False).head(n)
    log.info(f"🌶️  Seçilen {len(df)} volatil coin (botun canlı seçtiği tip):")
    for _, r in df.iterrows():
        log.info(f"   {r['symbol']:<22} %{r['pct']:>5.1f}  {r['vol_m']:>8.1f}M hacim")
    return df["symbol"].tolist()


def run_bucket(ex, name, symbols):
    """Bir coin kovası için baseline stratejiyi çalıştır → stats döndür + rapor."""
    bt.BT_SYMBOLS = symbols                    # load_data bu global'i okur
    dfmap, meta, btc1h = bt.load_data(ex)
    if not meta:
        log.info(f"  [{name}] veri yok"); return None
    entries = bt.gather_all_entries(meta, btc1h)
    trades  = bt.simulate_all(entries, dfmap)
    s = bt.stats(trades)
    if not s:
        log.info(f"  [{name}] hiç sinyal yok"); return None
    log.info("\n" + "─" * 60)
    log.info(f"  📦 KOVA: {name}   ({len(meta)} coin, {s['n']} işlem)")
    log.info(f"     WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  net={s['net']:+.1f}%  "
             f"ort+={s['avg_w']:+.1f}  ort-={s['avg_l']:+.1f}")
    from collections import defaultdict
    byc = defaultdict(lambda: [0.0, 0])
    for t in trades:
        byc[t["symbol"]][0] += t["net"]; byc[t["symbol"]][1] += 1
    log.info(f"     ── coin bazında net (kötüden iyiye) ──")
    for c, (v, cnt) in sorted(byc.items(), key=lambda x: x[1][0]):
        log.info(f"        {c:10} {v:>+7.1f}%  ({cnt} işlem)")
    return s


def main():
    log.info("📊 COIN SEÇİMİ testi — majör vs volatil (aynı strateji)")
    ex = bt.connect()
    vol_syms = pick_volatile(ex, VOLATILE_N, exclude=MAJORS)
    log.info("\n" + "═" * 60)
    sM = run_bucket(ex, "MAJÖRLER (likit)", MAJORS)
    sV = run_bucket(ex, "VOLATİL (botun seçtiği tip)", vol_syms) if vol_syms else None
    log.info("\n" + "═" * 60)
    log.info("  🎯 KARŞILAŞTIRMA")
    log.info("═" * 60)
    if sM: log.info(f"  MAJÖRLER : PF={sM['pf']:.2f}  WR=%{sM['wr']:.1f}  net={sM['net']:+.1f}%  ({sM['n']} işlem)")
    if sV: log.info(f"  VOLATİL  : PF={sV['pf']:.2f}  WR=%{sV['wr']:.1f}  net={sV['net']:+.1f}%  ({sV['n']} işlem)")
    if sM and sV:
        if sM["pf"] - sV["pf"] >= 0.25:
            log.info("  ✅ HİPOTEZ DOĞRU: majörlerde edge belirgin, volatilde eriyor.")
            log.info("     → Çözüm: coin filtresini sıkılaştır (min hacim/likidite, volatilite tavanı).")
        elif abs(sM["pf"] - sV["pf"]) < 0.25:
            log.info("  ⚪ Fark küçük: sorun coin seçiminde değil, başka yerde.")
        else:
            log.info("  ↩️  Beklenmedik: volatil kova daha iyi.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
