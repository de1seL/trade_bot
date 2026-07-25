"""
ADİL KARŞILAŞTIRMA — kullanıcının GERÇEK evreninde (volatil altcoinler),
ama "bugün volatil" seçim yanlılığı OLMADAN.

Sorun: bt_coins/bt_patlama'daki volatil kova "bugün oynayan" coinleri seçiyor →
ileriye-bakış yanlılığı → hem mevcut strateji hem Patlama şişiyor. Güvenilmez.

Çözüm: SABİT, köklü volatil altcoin listesi (bugünün hareketine göre seçilmedi,
uzun geçmişi var). Aynı liste üzerinde İKİ stratejiyi yan yana koştur:
    A) MEVCUT 5-koşul   (backtest.py beyni — stoch/rsi/macd/vol/st + ATR çıkış)
    B) PATLAMA 3-lü     (SuperTrend+Squeeze+VWAP + ST-flip çıkış)
Kalan hafif yanlılık (bugün listede olan coin = hayatta kalan) İKİSİNİ DE eşit
etkiler → karşılaştırma adil kalır.

Karar: hangisinin PF'si bu volatil evrende yüksekse O daha iyi. Mutlak seviye
hâlâ iyimser olabilir ama GÖRELİ sıralama güvenilir.

Çalıştırma:  python bt_fair.py   (Binance erişimi olan makinede)
"""
import backtest as bt
import bt_coins
import bt_patlama
import trade_bot as tb

log = tb.log

# Sabit volatil altcoin evreni — bugünün hareketine göre DEĞİL, köklü/volatil olduğu için.
# (Yoksa/kısa geçmişliyse load_data otomatik atlar.)
FIXED_VOLATILE = [f"{b}/USDT:USDT" for b in [
    "WIF", "1000PEPE", "1000BONK", "GALA", "KAITO", "SUI", "SEI", "ORDI",
    "PEOPLE", "ARB", "OP", "INJ", "TIA", "JUP", "WLD", "ENA", "PYTH", "JTO",
    "DYDX", "APT", "NEAR", "FIL", "AAVE", "CRV", "LDO", "RUNE", "GMT", "FET",
]]


def run_current(ex, symbols):
    """Mevcut 5-koşullu strateji (backtest.py beyni) — bt_coins.run_bucket kullanır."""
    return bt_coins.run_bucket(ex, "MEVCUT 5-koşul (stoch/rsi/macd/vol/st)", symbols)


def main():
    log.info("📊 ADİL KARŞILAŞTIRMA — sabit volatil evren (seçim yanlılığı yok)")
    log.info(f"   {len(FIXED_VOLATILE)} köklü volatil altcoin, aynı liste iki stratejide")
    ex = bt.connect()

    log.info("\n" + "═" * 62)
    log.info("  A) MEVCUT 5-KOŞULLU STRATEJİ")
    log.info("═" * 62)
    sc = run_current(ex, FIXED_VOLATILE)

    log.info("\n" + "═" * 62)
    log.info("  B) PATLAMA 3-LÜ (SuperTrend+Squeeze+VWAP)")
    log.info("═" * 62)
    sp = bt_patlama.run_bucket(ex, "PATLAMA 3-lü", FIXED_VOLATILE)

    log.info("\n" + "═" * 62)
    log.info("  🎯 ADİL SONUÇ — senin tarz coinlerde, yanlılıksız")
    log.info("═" * 62)
    if sc: log.info(f"  MEVCUT 5-koşul : PF={sc['pf']:.2f}  WR=%{sc['wr']:.1f}  net={sc['net']:+.1f}%  ({sc['n']})")
    if sp: log.info(f"  PATLAMA 3-lü   : PF={sp['pf']:.2f}  WR=%{sp['wr']:.1f}  net={sp['net']:+.1f}%  ({sp['n']})")
    if sc and sp:
        if sp['pf'] > sc['pf'] + 0.15:
            log.info("  ✅ PATLAMA daha iyi — bu evrende gerçekten üstün. Robustluk testi sırada.")
        elif sc['pf'] > sp['pf'] + 0.15:
            log.info("  ❌ MEVCUT daha iyi — Patlama'ya geçme, elindeki daha güçlü.")
        else:
            log.info("  ⚪ Başabaş — net fark yok, değiştirmeye değmez (basit olan kalsın).")
    log.info("═" * 62)


if __name__ == "__main__":
    main()
