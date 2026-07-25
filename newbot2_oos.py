"""
OUT-OF-SAMPLE doğrulama — overfitting kontrolü.

newbot2b sweep'i FIXED_VOLATILE'da EN İYİ varyant olarak şunu buldu:
    RSI(2)<3  +  Bollinger alt-band  +  ATRstop 3.0   → PF 2.72 (ama n=103, şüpheli)

Bu ayar o veriye FIT edildi. Gerçek mi test etmenin TEK yolu: ayarı DONDUR, hiç
görmediği BAŞKA coinlerde çalıştır. Tutarsa edge gerçek; çökerse overfitting'di.

Bu dosya donmuş ayarı 2 bağımsız evrende dener:
  1) OOS_VOLATILE — sweep'te OLMAYAN, farklı köklü volatil coinler
  2) LİKİT        — tamamen farklı karakter (ikinci kontrol)
Her biri için PF + iki-yarı. KARAR: OOS_VOLATILE'da PF ≥ 1.30 VE iki yarı >1
→ edge gerçek, canlı hazırlığı. Değilse → overfitting, dur.

Çalıştırma: python newbot2_oos.py
"""
import numpy as np
import backtest as bt
import trade_bot as tb
import newbot2b_bt as n2b        # donmuş motoru buradan kullan
import newbot_bt
import bt_fair

cfg = tb.CONFIG
log = tb.log

# DONMUŞ kazanan ayar (sweep'te seçildi — artık DEĞİŞMEZ)
FROZEN_RSI, FROZEN_BB, FROZEN_STOP = 3, True, 3.0

# Sweep'te OLMAYAN farklı volatil coinler (out-of-sample evren)
OOS_VOLATILE = [f"{b}/USDT:USDT" for b in [
    "FLOKI", "1000SHIB", "PENDLE", "ENS", "ONDO", "ETHFI", "STRK", "W",
    "MANTA", "JASMY", "GRT", "SAND", "MANA", "CHZ", "AXS", "APE", "GMX",
    "COMP", "SNX", "MKR", "EGLD", "FLOW", "CFX", "KAVA", "ROSE", "ALGO",
    "EOS", "HBAR",
]]


def run_universe(ex, name, symbols):
    allt = []; loaded = 0
    for sym in symbols:
        try:
            df = bt.fetch_tf(ex, sym, "1h", bt.BT_1H_LIMIT)
        except Exception:
            continue
        if len(df) < n2b.MIN_HIST:
            continue
        loaded += 1
        allt.extend(n2b.run_symbol(df, FROZEN_RSI, FROZEN_BB, FROZEN_STOP))
    s = n2b.pf_of(allt)
    log.info("\n" + "─" * 60)
    log.info(f"  📦 {name}  ({loaded} coin yüklendi)")
    if not s:
        log.info("     işlem yok"); return None
    s1 = n2b.pf_of([t for t in allt if t["half"] == 0])
    s2 = n2b.pf_of([t for t in allt if t["half"] == 1])
    p1 = s1["pf"] if s1 else 0; p2 = s2["pf"] if s2 else 0
    log.info(f"     n={s['n']}  WR=%{s['wr']:.1f}  PF={s['pf']:.2f}  net={s['net']:+.1f}%")
    log.info(f"     1.yarı PF={p1:.2f}   2.yarı PF={p2:.2f}")
    return s, p1, p2


def main():
    n2b.COST_FR = cfg["commission"] + cfg["slippage"]
    log.info("📊 OUT-OF-SAMPLE doğrulama — DONMUŞ ayar: RSI<3 + BB + stop3.0")
    log.info("   (bu ayar FIXED_VOLATILE'da seçildi; şimdi GÖRMEDİĞİ coinlerde test)")
    ex = bt.connect()
    rV = run_universe(ex, "OOS_VOLATILE (yeni coinler — asıl test)", OOS_VOLATILE)
    rL = run_universe(ex, "LİKİT (ikinci kontrol)", newbot_bt.LIQUID)
    log.info("\n" + "═" * 60)
    log.info("  🎯 OUT-OF-SAMPLE KARARI")
    log.info("═" * 60)
    if rV:
        s, p1, p2 = rV
        if s["pf"] >= 1.30 and p1 >= 1.0 and p2 >= 1.0 and s["n"] >= 60:
            log.info(f"  ✅ GEÇTİ: OOS volatilde PF {s['pf']:.2f}, iki yarı da >1 (n={s['n']}).")
            log.info("     Edge görmediği veride de tuttu → overfitting DEĞİL. Canlı hazırlığı konuşulur.")
        elif s["pf"] >= 1.15 and s["n"] >= 60:
            log.info(f"  ⚪ ZAYIF GEÇTİ: PF {s['pf']:.2f} (n={s['n']}). Umut var ama net değil.")
            log.info("     Daha çok veri/coin ile bir tur daha; canlıya HENÜZ geçme.")
        else:
            log.info(f"  ❌ ÇÖKTÜ: OOS volatilde PF {s['pf']:.2f} (n={s['n']}).")
            log.info("     2.72 overfitting'di — görmediği veride tutmadı. Canlıya GEÇME.")
    log.info("  Not: OOS testi geçmenin, in-sample 2.72'yi geçmekten çok daha değerli.")
    log.info("═" * 60)


if __name__ == "__main__":
    main()
