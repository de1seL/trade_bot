"""
╔══════════════════════════════════════════════════════════════╗
║   🤖 Kripto Futures Bot v10.0  — SIFIRDAN TEMİZ             ║
║   Borsa    : Binance USDT-M Futures                          ║
║   Kaldıraç : 5x                                             ║
╠══════════════════════════════════════════════════════════════╣

── STRATEJİ ────────────────────────────────────────────────────

  KATMAN 1 — GÜNLÜK TREND (1d EMA200)
    Fiyat > EMA200 → LONG bölgesi
    Fiyat < EMA200 → SHORT bölgesi

  KATMAN 2 — TREND GÜCÜ (4h ADX > 25)
    ADX < 25 → yatay piyasa → giriş yok

  KATMAN 3 — MOMENTUM (4h EMA hizalama)
    EMA20 > EMA50 → yukarı momentum (LONG)
    EMA20 < EMA50 → aşağı momentum (SHORT)

  KATMAN 4 — GİRİŞ (1h, min koşul + ZORUNLU taze tetik)
    Skor koşulları (5): StochRSI dönüş, RSI momentum, MACD crossover,
                        Hacim artışı, Süper Trend yönü
    Tetik (≥1 şart): MACD crossover VEYA StochRSI dönüşü
    Tüm sinyaller KAPANMIŞ mumdan hesaplanır (repaint yok)

── ÇIKIŞ ────────────────────────────────────────────────────────
  SL      : ATR × 1.3  (min %1.2, max %3.0) — 1h gürültüsünün dışında, DARALTILMAZ
  TP      : giriş ± (gerçek SL mesafesi × 1.5)  → R:R 1:1.5 (ulaşılabilir)
  ROI TP  : +%3.5 kaldıraçlı kâr → direkt kapat (roi_tp_enabled ile aç/kapa, varsayılan KAPALI)
  Breakeven: +1R kârda SL → giriş fiyatına (R-bazlı)
  Trailing: +1R kârda devreye girer, %1.2 band, asla girişin altına inmez
  Zaman   : 4 saat içinde kapanmazsa çık

── KORUMALAR ─────────────────────────────────────────────────────
  • Günlük %8 zarar limiti
  • SL sonrası 1 saat cooldown
  • TP sonrası 10 dk cooldown
  • Max 8 eşzamanlı pozisyon
  • NaN koruması (tüm indikatörler)
  • Komisyon + slippage dahil PnL
"""

import os
import time
import logging
from datetime import date

import ccxt
import numpy as np
import pandas as pd
import ta
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────

CONFIG = {
    # ── Coinler ─────────────────────────────────────────────
    # HİBRİT TARAMA: ana coinler HER ZAMAN + en volatil coinler SAATLİK rotasyon.
    #   "symbols"      BOŞ → dinamik mod açık (hibrit çalışır)
    #   "core_symbols" → her zaman taranan sabit ana coinler (BTC/ETH/BNB...)
    #   dinamik kısım  → en volatil top_volatile_count coin, saatte bir yenilenir
    # Tamamen sabit liste istersen coinleri "symbols"e yaz (o zaman dinamik kapanır).
    "symbols"             : [],
    "core_symbols"        : [   # SABİT kalır, hiç düşmez
        "BTC/USDT:USDT",  "ETH/USDT:USDT",  "BNB/USDT:USDT",
        "SOL/USDT:USDT",  "XRP/USDT:USDT",  "DOGE/USDT:USDT",
        "ADA/USDT:USDT",  "AVAX/USDT:USDT", "LINK/USDT:USDT",
        "DOT/USDT:USDT",
    ],
    "top_volatile_count"  : 40,          # ana coinlere EK olarak taranacak volatil coin sayısı
    "symbol_refresh_sec"  : 3600,        # volatil kısım saatte bir yenilenir

    # ── Tarama filtreleri ───────────────────────────────────
    # Az hareket eden büyük-cap'leri dışla (küçük sermaye + 5x ile kâr çıkmaz).
    "exclude_bases"       : ["BTC", "BNB"],   # bu coinleri HİÇ tarama (istersen ETH vb. ekle)
    "min_volatility_pct"  : 4.0,         # 24s |%değişim| < %4 olanları ELE → "gibi" durgunlar
                                         #   (ETH gibi az oynayanlar bu filtreyle zaten çıkar)
    "min_listing_days"    : 45,          # 45 günden YENİ coinleri tarama → yeterli geçmiş yok
                                         #   (4h EMA200 için ~36 gün şart; "trend verisi eksik"i önler)

    # ── Kaldıraç ────────────────────────────────────────────
    "leverage"            : 10,

    # ── Zaman dilimleri ─────────────────────────────────────
    "daily_tf"            : "1d",
    "trend_tf"            : "4h",
    "entry_tf"            : "1h",

    # ── Trend (4h) ───────────────────────────────────────────
    "ema_trend"           : 200,
    "ema_fast"            : 20,
    "ema_slow"            : 50,

    # ── ADX (4h) — trend gücü ────────────────────────────────
    "adx_period"          : 14,
    "adx_threshold"       : 25,          # 20 çok zayıftı; 25 = klasik "güçlü trend" eşiği

    # ── Stochastic RSI (1h) ──────────────────────────────────
    "stoch_period"        : 14,
    "stoch_smooth_k"      : 3,
    "stoch_smooth_d"      : 3,
    "stoch_oversold"      : 40,          # LONG için StochRSI > 40 (momentum var)
    "stoch_overbought"    : 60,          # SHORT için StochRSI < 60

    # ── RSI (1h) ─────────────────────────────────────────────
    "rsi_period"          : 14,
    "rsi_oversold"        : 45,          # LONG için RSI > 45 (trend momentumu var)
    "rsi_overbought"      : 55,          # SHORT için RSI < 55

    # ── MACD (1h) ────────────────────────────────────────────
    "macd_fast"           : 12,
    "macd_slow"           : 26,
    "macd_sig"            : 9,
    "macd_lookback"       : 5,    # daha güvenilir crossover

    # ── Süper Trend (1h) ─────────────────────────────────────
    "st_period"           : 10,
    "st_mult"             : 3.0,

    # ── Hacim (1h) ───────────────────────────────────────────
    "vol_period"          : 20,
    "vol_mult"            : 1.0,

    # ── ATR & SL/TP (1h) ─────────────────────────────────────
    "atr_period"          : 14,
    "atr_sl_mult"         : 1.3,         # SL'i 1h gürültüsünün DIŞINA koy (eski 0.8 çok dardı)
    "rr_ratio"            : 1.5,         # TP = giriş ± 1.5 × gerçek SL mesafesi. 2.0 idi ama
                                         # fiyat oraya çoğu zaman ulaşamadan dönüyordu; 1.5 daha
                                         # ulaşılabilir → daha yüksek isabet. SL'e DOKUNMUYORUZ.
    "min_sl_pct"          : 0.012,       # %1.2 min — 5x'te gürültüye stop olmayı önler
    "max_sl_pct"          : 0.030,       # %3.0 max

    # ── Trailing & Breakeven (R-bazlı) ───────────────────────
    # Eşikler artık sabit % değil, işlemin KENDİ risk mesafesine (1R) göre ölçeklenir.
    # Böylece SL'i %1.2 olan da %3.0 olan da tutarlı yönetilir.
    # Sıra önemli: önce breakeven (giriş kilidi), SONRA trailing devreye girer —
    # trailing SL'i ASLA girişin altına çekmez (kazananı zarara çevirmeyi önler).
    "breakeven_at_r"      : 1.0,         # +1R kârda SL → giriş (kilit)
    "trail_start_r"       : 1.0,         # +1R kârda trailing başlar
    "trail_pct"           : 0.012,       # trailing bandı (fiyatın altında %1.2)
    "trail_max_pct"       : 0.025,

    # ── Giriş eşiği ─────────────────────────────────────────
    "min_conditions"      : 3,    # 6 koşuldan kaçı sağlanmalı
    "require_trigger"     : True, # Skor yetmez: taze bir TETİK (MACD crossover veya
                                  # StochRSI dönüşü) de şart. Aksi halde uzamış hareketin
                                  # ortasından/tepesinden giriyorsun (st/obv durum koşulları
                                  # trend yönünde zaten bedava True oluyor).

    # ── Risk ─────────────────────────────────────────────────
    "trade_usdt"          : 10,
    "max_positions"       : 2,
    # Günlük ZARAR limiti KAPALI (kullanıcı kaldırdı) — -%8'de durma yok.
    "daily_loss_enabled"  : False,
    "daily_loss_pct"      : 8.0,           # (sadece daily_loss_enabled True ise geçerli)
    # Günlük KÂR hedefi: +%X'e ulaşınca N saat YENİ İŞLEM açma (açık pozisyonlar yönetilir).
    "daily_profit_target_pct": 20.0,       # +%20 günlük kâr
    "profit_pause_hours"     : 12,         # → 12 saat yeni işlem yok
    "balance_refresh_sec" : 300,          # #5 günlük % CANLI bakiyeye göre (5 dk'da bir yenile)
    "cooldown_sl_sec"     : 3600,
    "cooldown_tp_sec"     : 600,
    "max_pos_hours"       : 4,            # 4 saat içinde kapanmazsa çık
    "max_spread_pct"      : 0.0015,       # #6 giriş öncesi spread > %0.15 ise atla (likidite)

    # ── #2 Trailing'i borsaya yansıt ─────────────────────────
    # Trailing SL ilerledikçe borsadaki STOP emrini güncelle → bot çökse bile
    # trailing kârın korunur. Her küçük harekette değil, eşik kadar oynayınca.
    "sync_trailing_to_exchange": True,
    "sl_sync_threshold_pct"    : 0.003,   # SL %0.3'ten fazla oynadıysa borsada güncelle

    # ── #3 OHLCV cache (API yükü/ban riski azaltır) ──────────
    # Yüksek zaman dilimleri sık değişmez; her döngüde yeniden çekme.
    "cache_1d_sec"        : 3600,         # 1d mum saatte bir yenilensin
    "cache_4h_sec"        : 900,          # 4h mum 15 dk'da bir
    "cache_1h_sec"        : 60,           # 1h mum 1 dk'da bir

    # ── Komisyon ─────────────────────────────────────────────
    "commission"          : 0.0004,
    "slippage"            : 0.0002,

    # ── BTC Korelasyon Filtresi ──────────────────────────────
    "btc_filter_enabled"  : True,
    "btc_drop_threshold"  : 0.01,        # BTC son 1 saatte %1+ düştüyse LONG açma
    "btc_pump_threshold"  : 0.01,        # BTC son 1 saatte %1+ yükseldiyse SHORT açma
    "btc_exit_threshold"  : 0.02,        # BTC -%2+ düşünce açık LONG pozisyonları kapat

    # ── YENİ: ROI TP ──────────────────────────────────────────
    "roi_tp_enabled"      : False,
    "roi_tp_pct"          : 0.035,       # +%3.5 kaldıraçlı kâr → direkt kapat

    # ── Sistem ───────────────────────────────────────────────
    "loop_sec"            : 15,          # 60'tan 15'e indirildi — SL daha hızlı tetiklenir
    "dry_run"             : False,
}

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("trade_bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PNL TRACKER
# ─────────────────────────────────────────────────────────────

class PnLTracker:
    def __init__(self):
        self.session_pnl = 0.0
        self.daily_pnl   = 0.0
        self.daily_date  = date.today()
        self.total       = 0
        self.wins        = 0
        self.losses      = 0

    def _roll_day_if_needed(self):
        """Gün değiştiyse günlük PnL'i sıfırla. Hem işlem kaydında hem limit
        kontrolünde çağrılır — böylece bot duraklarken gün dönünce kendi devam eder."""
        if date.today() != self.daily_date:
            self.daily_pnl  = 0.0
            self.daily_date = date.today()

    def record(self, pnl_pct: float, usdt: float):
        pnl_usdt = usdt * pnl_pct / 100
        self.session_pnl += pnl_usdt
        self.total       += 1
        self._roll_day_if_needed()
        self.daily_pnl += pnl_usdt
        if pnl_pct >= 0:
            self.wins += 1
        else:
            self.losses += 1
        wr = self.wins / self.total * 100 if self.total else 0
        log.info(
            f"📊 PNL | Oturum: {self.session_pnl:+.2f} USDT  "
            f"Günlük: {self.daily_pnl:+.2f} USDT  "
            f"Win Rate: %{wr:.0f} ({self.wins}W/{self.losses}L)"
        )

    def daily_limit_hit(self, balance: float) -> bool:
        # ÖNEMLİ: önce gün dönüşünü kontrol et. Yoksa limite takılınca bot durur ve
        # daily_pnl yalnızca record()'da sıfırlandığı için (duraklarken işlem yok)
        # ertesi gün bile açılmaz — kalıcı kilit. Bu satır o kilidi önler.
        self._roll_day_if_needed()
        if balance <= 0:
            return False
        if self.daily_pnl < 0 and abs(self.daily_pnl) / balance * 100 >= CONFIG["daily_loss_pct"]:
            log.warning(f"🛑 Günlük zarar limiti → 1 saat duruyor")
            return True
        return False

    def daily_profit_hit(self, balance: float, target_pct: float) -> bool:
        """Günlük KÂR hedefe ulaştı mı? (bakiyenin +%target'ı)."""
        self._roll_day_if_needed()
        if balance <= 0:
            return False
        return self.daily_pnl > 0 and (self.daily_pnl / balance * 100) >= target_pct

pnl_tracker   = PnLTracker()
START_BALANCE = 0.0

# ─────────────────────────────────────────────────────────────
# BORSA
# ─────────────────────────────────────────────────────────────

def connect_exchange() -> ccxt.binance:
    ex = ccxt.binance({
        "apiKey"         : os.getenv("BINANCE_API_KEY", ""),
        "secret"         : os.getenv("BINANCE_SECRET", ""),
        "options"        : {"defaultType": "future"},
        "enableRateLimit": True,
    })
    if not CONFIG["dry_run"]:
        # Marketleri yükle — precision/min-amount kontrolleri buna dayanır
        try:
            ex.load_markets()
        except Exception as e:
            log.warning(f"⚠️  Marketler şimdi yüklenemedi (sonra lazy yüklenecek): {e}")
        # Bu bot one-way (reduceOnly) mantığı üzerine kurulu; hedge modda kırılır.
        try:
            ex.set_position_mode(False)   # False = one-way
            log.info("✅ Pozisyon modu: one-way")
        except Exception as e:
            # Zaten one-way ise ya da açık pozisyon varsa hata verir — kritik değil
            log.info(f"ℹ️  Pozisyon modu zaten ayarlı görünüyor (one-way): {e}")
    log.info("✅ Binance USDT-M Futures bağlandı")
    return ex


def fetch_balance(ex: ccxt.Exchange) -> float:
    if CONFIG["dry_run"]:
        bal = CONFIG["trade_usdt"] * 20
        log.info(f"[DRY RUN] Tahmini bakiye: {bal:.2f} USDT")
        return bal
    try:
        b = ex.fetch_balance()
        u = float(b["USDT"]["free"])
        log.info(f"💰 Bakiye: {u:.2f} USDT")
        return u
    except Exception as e:
        log.error(f"❌ Bakiye çekilemedi, bot güvenlik için durduruluyor: {e}")
        raise SystemExit(
            "Gerçek bakiye okunamadı (API key/secret veya bağlantı sorunu olabilir). "
            "Sahte bakiyeyle canlı modda devam etmek riskli olduğu için bot durduruldu."
        )


def setup_symbol(ex: ccxt.Exchange, symbol: str, leverage: int):
    if CONFIG["dry_run"]:
        return
    try:
        ex.set_leverage(leverage, symbol)
    except Exception as e:
        log.warning(f"⚠️  {symbol} kaldıraç ayarlanamadı: {e}")
    try:
        ex.set_margin_mode("isolated", symbol)
    except Exception as e:
        # -4046 "No need to change margin type" zaten isolated demektir, zararsız
        if "4046" not in str(e) and "No need" not in str(e):
            log.warning(f"⚠️  {symbol} margin modu: {e}")


def ensure_leverage(ex: ccxt.Exchange, symbol: str, leverage: int) -> bool:
    """Pozisyon açmadan HEMEN ÖNCE kaldıracı ayarlar ve doğrular.
    Ayarlanamazsa False döner → çağıran pozisyon AÇMAZ. Böylece kaldıraç
    ayarı sessizce başarısız olunca hesabın mevcut (belki 20x) kaldıracıyla
    yanlışlıkla işlem açma riski ortadan kalkar."""
    if CONFIG["dry_run"]:
        return True
    try:
        ex.set_leverage(leverage, symbol)
        return True
    except Exception as e:
        msg = str(e)
        # Zaten istenen kaldıraçtaysa Binance bazen "no need to change" der → sorun değil
        if "no need" in msg.lower() or "-4046" in msg:
            return True
        log.error(f"🚫 [{symbol}] Kaldıraç {leverage}x doğrulanamadı → pozisyon AÇILMAYACAK: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# SEMBOL SEÇİCİ
# ─────────────────────────────────────────────────────────────

STABLE   = {"USDT","BUSD","USDC","DAI","TUSD","FDUSD","USDP","UST"}
# Tarama hiç sonuç vermezse yedek liste — BTC/BNB gibi durgunlar dahil DEĞİL (hareketli alt'lar)
FALLBACK = ["SOL/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT"]


def _listed_long_enough(m: dict, now_ms: int, min_age_ms: int) -> bool:
    """Coin yeterince eski mi? Binance listeleme tarihine (onboardDate) bakar.
    Yeni coinlerde 4h EMA200/ADX için yeterli mum olmaz → 'trend verisi eksik'.
    Bilgi yoksa eleme yapma (True)."""
    if min_age_ms <= 0:
        return True
    ob = (m.get("info") or {}).get("onboardDate")
    try:
        return ob is None or (now_ms - int(ob)) >= min_age_ms
    except Exception:
        return True


def filter_min_leverage(ex, symbols: list[str], min_lev: int) -> list[str]:
    """Borsada max kaldıracı min_lev (5x) altında olan coinleri listeden çıkarır.
    Tek bir fetch_leverage_tiers çağrısıyla tüm semboller okunur. dry_run'da veya
    bilgi alınamazsa dokunmaz (girişte ensure_leverage yine koruma sağlar)."""
    if CONFIG["dry_run"] or not symbols:
        return symbols
    try:
        tiers = ex.fetch_leverage_tiers(symbols)
    except Exception as e:
        log.warning(f"⚠️  Kaldıraç filtresi atlandı (bilgi alınamadı): {e}")
        return symbols
    ok, dropped = [], []
    for s in symbols:
        ts = tiers.get(s) or []
        try:
            maxlev = max((t.get("maxLeverage") or 0) for t in ts) if ts else 0
        except Exception:
            maxlev = 0
        # Bilgi yoksa (maxlev=0) tutma tarafında kal; varsa ve < min_lev ise çıkar
        if maxlev == 0 or maxlev >= min_lev:
            ok.append(s)
        else:
            dropped.append(f"{s.split('/')[0]}({maxlev}x)")
    if dropped:
        log.info(f"⛔ {min_lev}x desteklemeyen, çıkarıldı: {', '.join(dropped)}")
    return ok


def get_symbols(ex: ccxt.Exchange, top_n: int) -> list[str]:
    log.info("🔍 Coin taraması başlıyor...")
    try:
        markets = ex.load_markets()
        tickers = ex.fetch_tickers()
    except Exception as e:
        log.error(f"Tarama hatası: {e}")
        return FALLBACK

    exclude = {b.upper() for b in CONFIG.get("exclude_bases", [])}
    now_ms     = ex.milliseconds()
    min_age_ms = CONFIG.get("min_listing_days", 0) * 86_400_000
    valid = {
        m["symbol"] for m in markets.values()
        if m.get("type") == "swap" and m.get("linear")
        and m.get("active") and m.get("quote") == "USDT"
        and m.get("base") not in STABLE
        and m.get("base") not in exclude          # BTC/BNB gibi dışlananları ele
        and _listed_long_enough(m, now_ms, min_age_ms)   # yeni coinleri (yetersiz geçmiş) ele
    }

    min_vol_pct = CONFIG.get("min_volatility_pct", 0.0)
    rows = []
    for sym, t in tickers.items():
        if sym not in valid:
            continue
        vol  = t.get("quoteVolume") or 0
        spct = t.get("percentage") or 0          # işaretli 24s değişim (yön için)
        pct  = abs(spct)
        if vol < 10_000_000:  # min 10M USDT hacim
            continue
        if pct < min_vol_pct:  # 24s hareketi çok az → durgun coin, ele
            continue
        rows.append({"symbol": sym, "pct": pct, "spct": spct, "vol_m": vol / 1e6, "score": pct * vol})

    if not rows:
        return FALLBACK

    df = pd.DataFrame(rows).sort_values("score", ascending=False)

    # ── 5x desteklemeyenleri ELE, sonra top_n al (yerlerine başka coin gelir) ──
    ranked = filter_min_leverage(ex, df["symbol"].tolist(), CONFIG["leverage"])
    df = df[df["symbol"].isin(ranked)]
    # 3) Kalanların en volatil top_n'i → liste hep dolu kalır
    df = df.sort_values("score", ascending=False).head(top_n)
    if df.empty:
        return FALLBACK

    # ── Rejim özeti ──────────────────────────────────────────
    # Tarayıcı en çok HAREKET edeni seçer. Kırmızı günde bunlar düşenlerdir →
    # bot ağırlıkla SHORT arar (bu bir hata değil, piyasa böyle).
    ups   = int((df["spct"] > 0).sum())
    downs = int((df["spct"] < 0).sum())
    if downs > ups * 2:
        rejim = "📉 DÜŞÜŞ ağırlıklı → çoğunlukla SHORT beklenir (normal)"
    elif ups > downs * 2:
        rejim = "📈 YÜKSELİŞ ağırlıklı → çoğunlukla LONG beklenir"
    else:
        rejim = "↔️  karışık → her iki yön de mümkün"
    log.info(f"🧭 Piyasa rejimi: seçilen {len(df)} coinin {ups}'i ↑ / {downs}'i ↓   {rejim}")

    log.info(f"🏆 En volatil {len(df)} coin (hepsi taranacak, max {CONFIG['max_positions']} pozisyon açılacak):")
    for _, r in df.iterrows():
        ok = "↑" if r["spct"] > 0 else "↓"
        log.info(f"   {r['symbol']:<28}  {ok}%{r['pct']:>5.1f}  {r['vol_m']:>8.1f}M")
    return df["symbol"].tolist()


def build_scan_list(ex) -> list[str]:
    """Taranacak coin listesini kurar:
      • "symbols" doluysa → tam o sabit liste (dinamik kapalı).
      • boşsa → core_symbols (sabit ANA coinler) + en volatil top_n (saatlik rotasyon).
    Ana coinler her zaman başta ve listede kalır; volatil kısım saatte bir değişir."""
    cfg = CONFIG
    if cfg["symbols"]:
        return list(dict.fromkeys(cfg["symbols"]))
    core = list(cfg.get("core_symbols", []))
    dyn  = get_symbols(ex, cfg["top_volatile_count"])
    merged = list(dict.fromkeys(core + dyn))   # ana coinler önce, tekrarsız
    log.info(f"🧩 Tarama listesi: {len(core)} ana coin (sabit) + {len(merged)-len(core)} volatil = {len(merged)} coin")
    return merged

# ─────────────────────────────────────────────────────────────
# VERİ
# ─────────────────────────────────────────────────────────────

def fetch_ohlcv(ex: ccxt.Exchange, symbol: str, tf: str, limit: int = 300) -> pd.DataFrame:
    raw = ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    df  = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("ts", inplace=True)
    return df


# #3: OHLCV cache — yüksek zaman dilimleri (1d/4h) her döngüde değişmez.
# (symbol, tf) → (çekildiği_zaman, df). TTL içinde aynı df'i döner, API'yi yormaz.
_OHLCV_CACHE: dict = {}

def fetch_ohlcv_cached(ex, symbol: str, tf: str, limit: int, ttl: float) -> pd.DataFrame:
    key = (symbol, tf)
    now = time.time()
    hit = _OHLCV_CACHE.get(key)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    df = fetch_ohlcv(ex, symbol, tf, limit)
    _OHLCV_CACHE[key] = (now, df)
    return df


def get_btc_change(ex: ccxt.Exchange) -> float:
    """BTC'nin son 1 saatteki fiyat değişimini döner."""
    try:
        df = fetch_ohlcv(ex, "BTC/USDT:USDT", "1h", limit=3)
        if len(df) < 2:
            return 0.0
        prev = float(df["close"].iloc[-2])
        curr = float(df["close"].iloc[-1])
        return (curr - prev) / prev
    except Exception:
        return 0.0


def fetch_current_price(ex, symbol) -> float:
    """Anlık fiyatı ticker'dan alır, hata olursa None döner."""
    try:
        return float(ex.fetch_ticker(symbol)["last"])
    except Exception:
        return None


def spread_ok(ex, symbol, max_spread: float) -> bool:
    """#6: Giriş öncesi bid/ask spread'ini kontrol eder. Spread çok genişse
    (düşük likidite) market emri fazla kayar → o girişi atla. Bilgi yoksa
    veya hata olursa engellemez (True)."""
    if CONFIG["dry_run"]:
        return True
    try:
        t   = ex.fetch_ticker(symbol)
        bid = t.get("bid"); ask = t.get("ask")
        if not bid or not ask:
            return True
        spread = (float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2)
        if spread > max_spread:
            log.info(f"⏭️  [{symbol}] Spread %{spread*100:.3f} > %{max_spread*100:.3f} → likidite düşük, atla")
            return False
        return True
    except Exception:
        return True


def fetch_balance_quiet(ex):
    """#5: Bakiyeyi sessizce (SystemExit fırlatmadan) okur. Periyodik yenileme
    için — hata olursa None döner, çağıran eski değeri korur."""
    if CONFIG["dry_run"]:
        return None
    try:
        b = ex.fetch_balance()
        return float(b["USDT"]["free"])
    except Exception as e:
        log.warning(f"⚠️  Bakiye yenilenemedi (eski değer kullanılıyor): {e}")
        return None

# ─────────────────────────────────────────────────────────────
# İNDİKATÖRLER
# ─────────────────────────────────────────────────────────────

def calc_daily_trend(df: pd.DataFrame) -> str:
    ema200 = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
    if pd.isna(ema200.iloc[-1]):
        return "NONE"
    price = float(df["close"].iloc[-1])
    if price > float(ema200.iloc[-1]):
        return "LONG"
    elif price < float(ema200.iloc[-1]):
        return "SHORT"
    return "NONE"


def calc_trend(df: pd.DataFrame) -> dict | None:
    """4h trend: EMA hizalama + ADX güç kontrolü"""
    cfg = CONFIG
    c   = df["close"]

    # Yeni listelenmiş coinlerde yeterli geçmiş olmayabilir. ta'nın ADX'i kısa
    # seride NaN dönmek yerine IndexError fırlatıyor → önce uzunluğu garanti et.
    if len(df) < cfg["ema_trend"] + cfg["adx_period"]:
        return None

    ema200 = ta.trend.EMAIndicator(c, window=cfg["ema_trend"]).ema_indicator()
    ema20  = ta.trend.EMAIndicator(c, window=cfg["ema_fast"]).ema_indicator()
    ema50  = ta.trend.EMAIndicator(c, window=cfg["ema_slow"]).ema_indicator()
    adx    = ta.trend.ADXIndicator(df["high"], df["low"], c, window=cfg["adx_period"]).adx()

    # NaN kontrolü
    for s in [ema200, ema20, ema50, adx]:
        if pd.isna(s.iloc[-1]):
            return None

    price   = float(c.iloc[-1])
    e200    = float(ema200.iloc[-1])
    e20     = float(ema20.iloc[-1])
    e50     = float(ema50.iloc[-1])
    adx_val = float(adx.iloc[-1])

    if e20 > e50:
        direction = "LONG"
    elif e20 < e50:
        direction = "SHORT"
    else:
        direction = "NONE"

    return {
        "direction": direction,
        "ema200"   : round(e200, 6),
        "ema20"    : round(e20,  6),
        "ema50"    : round(e50,  6),
        "adx"      : round(adx_val, 1),
        "adx_ok"   : adx_val >= cfg["adx_threshold"],
        "price"    : round(price, 6),
    }


def calc_entry(df: pd.DataFrame) -> dict | None:
    """1h giriş indikatörleri"""
    cfg = CONFIG

    # Kısa geçmişli (yeni) coinlerde indikatörler çökebilir → yeterli mum yoksa atla
    if len(df) < max(cfg["stoch_period"], cfg["rsi_period"], cfg["macd_slow"],
                     cfg["atr_period"], cfg["vol_period"]) + 5:
        return None

    # Stochastic RSI
    stoch = ta.momentum.StochRSIIndicator(
        df["close"], window=cfg["stoch_period"],
        smooth1=cfg["stoch_smooth_k"], smooth2=cfg["stoch_smooth_d"]
    )
    df["sk"] = stoch.stochrsi_k() * 100
    df["sd"] = stoch.stochrsi_d() * 100

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(
        df["close"], window=cfg["rsi_period"]
    ).rsi()

    # MACD
    macd_obj    = ta.trend.MACD(df["close"], window_slow=cfg["macd_slow"], window_fast=cfg["macd_fast"], window_sign=cfg["macd_sig"])
    df["macd"]  = macd_obj.macd()
    df["msig"]  = macd_obj.macd_signal()

    # Süper Trend (vektörel)
    atr_st = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=cfg["st_period"]
    ).average_true_range()
    hl2    = (df["high"] + df["low"]) / 2
    ur = (hl2 + cfg["st_mult"] * atr_st).values
    lr = (hl2 - cfg["st_mult"] * atr_st).values
    cl = df["close"].values
    u  = ur.copy(); lo = lr.copy()
    st = ur.copy() * np.nan
    sd = np.ones(len(df), dtype=int)
    for i in range(1, len(df)):
        u[i]  = ur[i] if (ur[i] < u[i-1]  or cl[i-1] > u[i-1])  else u[i-1]
        lo[i] = lr[i] if (lr[i] > lo[i-1] or cl[i-1] < lo[i-1]) else lo[i-1]
        if i < cfg["st_period"]:
            st[i] = np.nan; sd[i] = 1
        elif sd[i-1] == 1:
            sd[i] = -1 if cl[i] < lo[i] else 1
        else:
            sd[i] =  1 if cl[i] > u[i]  else -1
        st[i] = lo[i] if sd[i] == 1 else u[i]
    df["st"]  = st
    df["std"] = sd

    # ATR & Hacim
    df["atr"]   = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=cfg["atr_period"]
    ).average_true_range()
    df["vol_ma"] = df["volume"].rolling(cfg["vol_period"]).mean()

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    price = float(last["close"])

    # Coin kendi 1h momentum kontrolü
    coin_chg_1h = (price - float(prev["close"])) / float(prev["close"])

    # NaN Koruması
    for col in ["sk","sd","macd","msig","st","atr","vol_ma","rsi"]:
        if pd.isna(last[col]):
            return None

    # MACD Crossover
    lb   = cfg["macd_lookback"]
    win  = df.tail(lb + 1)
    macd_up = macd_down = False
    for i in range(len(win) - 1):
        p = win.iloc[i]; c = win.iloc[i+1]
        if p["macd"] <= p["msig"] and c["macd"] > c["msig"]:
            macd_up   = True
        if p["macd"] >= p["msig"] and c["macd"] < c["msig"]:
            macd_down = True

    sk = float(last["sk"]); sd2 = float(last["sd"])
    # StochRSI: aşırı bölgede + K D'nin üstünde + son 3 mumda yükseliyor
    stoch_series = df["sk"].dropna()
    sk_rising  = len(stoch_series) >= 3 and float(stoch_series.iloc[-1]) > float(stoch_series.iloc[-3])
    sk_falling = len(stoch_series) >= 3 and float(stoch_series.iloc[-1]) < float(stoch_series.iloc[-3])
    # StochRSI: trend momentumu — LONG için yükseliyor, SHORT için düşüyor
    stoch_long  = sk > cfg["stoch_oversold"]  and sk > sd2 and sk_rising
    stoch_short = sk < cfg["stoch_overbought"] and sk < sd2 and sk_falling

    rsi_val   = float(last["rsi"])
    # RSI kendi momentumuna baksın (eskiden sk_rising'e bağlıydı → StochRSI'ın kopyasıydı,
    # yani 6 koşuldan biri sahteydi). Artık bağımsız bir teyit.
    rsi_series  = df["rsi"].dropna()
    rsi_rising  = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) > float(rsi_series.iloc[-3])
    rsi_falling = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) < float(rsi_series.iloc[-3])
    # Trend takip: LONG için RSI yükseliyor ve 45 üstünde, SHORT için düşüyor ve 55 altında
    rsi_long  = rsi_val > cfg["rsi_oversold"]   and rsi_rising
    rsi_short = rsi_val < cfg["rsi_overbought"] and rsi_falling

    st_long  = int(last["std"]) == 1
    st_short = int(last["std"]) == -1
    vol_ok   = float(last["volume"]) > float(last["vol_ma"]) * cfg["vol_mult"]

    # Skor: StochRSI + RSI + MACD + Hacim + ST (5 koşul; OBV kaldırıldı — perp'te
    # zayıf/yanıltıcı ve EMA trendiyle zaten örtüşüyordu)
    long_score  = sum([stoch_long,  rsi_long,  macd_up,   vol_ok, st_long])
    short_score = sum([stoch_short, rsi_short, macd_down, vol_ok, st_short])

    # TETİK = taze zamanlama olayı (durum koşulu değil). Girişi geç/uzamış
    # hareketten korur. MACD crossover ya da StochRSI momentum dönüşü.
    long_trigger  = macd_up   or stoch_long
    short_trigger = macd_down or stoch_short

    return {
        "price"       : round(price, 6),
        "atr"         : round(float(last["atr"]), 6),
        "coin_chg_1h" : round(coin_chg_1h, 4),
        "sk"          : round(sk, 1),
        "sd"          : round(sd2, 1),
        "rsi"         : round(rsi_val, 1),
        "rsi_long"    : rsi_long,
        "rsi_short"   : rsi_short,
        "macd"        : round(float(last["macd"]), 6),
        "msig"        : round(float(last["msig"]), 6),
        "st_val"      : round(float(last["st"]), 6),
        "st_long"     : st_long,
        "st_short"    : st_short,
        "stoch_long"  : stoch_long,
        "stoch_short" : stoch_short,
        "macd_up"     : macd_up,
        "macd_down"   : macd_down,
        "vol_ok"      : vol_ok,
        "volume"      : float(last["volume"]),
        "vol_ma"      : float(last["vol_ma"]),
        "long_score"  : long_score,
        "short_score" : short_score,
        "long_trigger"  : long_trigger,
        "short_trigger" : short_trigger,
    }


def calc_1h_trend(df) -> str:
    """1h EMA20/50 hizalaması — zaman dilimi uyum kontrolü için."""
    ema20 = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    if pd.isna(ema20.iloc[-1]) or pd.isna(ema50.iloc[-1]):
        return "NONE"
    if float(ema20.iloc[-1]) > float(ema50.iloc[-1]):
        return "LONG"
    elif float(ema20.iloc[-1]) < float(ema50.iloc[-1]):
        return "SHORT"
    return "NONE"


def get_signal(trend: dict, entry: dict, daily: str, btc_chg: float = 0.0,
               trend_1h: str = "NONE") -> str:
    cfg = CONFIG
    d   = trend["direction"]

    if d == "NONE":          return "HOLD"
    if not trend["adx_ok"]: return "HOLD"

    # ── Coin momentum filtresi ───────────────────────────────
    # Coin son 1 saatte sert düştüyse LONG açma, sert yükseldiyse SHORT açma
    coin_chg = entry.get("coin_chg_1h", 0.0)
    if d == "LONG"  and coin_chg <= -0.015: return "HOLD"  # -%1.5 düştü → LONG açma
    if d == "SHORT" and coin_chg >=  0.015: return "HOLD"  # +%1.5 yükseldi → SHORT açma

    # ── Zaman Dilimi Uyum Kontrolü ───────────────────────────
    # 1d ve 4h ters → kesinlikle giriş yok
    if daily != "NONE" and daily != d: return "HOLD"
    # 1h ters → daha seçici (1 ekstra koşul gerekli)
    min_c = cfg["min_conditions"]
    if trend_1h != "NONE" and trend_1h != d:
        min_c += 1

    # ── BTC Korelasyon Filtresi ──────────────────────────────
    if cfg["btc_filter_enabled"]:
        if d == "LONG"  and btc_chg <= -cfg["btc_drop_threshold"]:
            return "HOLD"
        if d == "SHORT" and btc_chg >=  cfg["btc_pump_threshold"]:
            return "HOLD"

    # ── Taze tetik şartı ─────────────────────────────────────
    # Skor yetse bile zamanlama tetiği yoksa girme (uzamış hareket koruması).
    if cfg.get("require_trigger", True):
        if d == "LONG"  and not entry.get("long_trigger"):  return "HOLD"
        if d == "SHORT" and not entry.get("short_trigger"): return "HOLD"

    if d == "LONG"  and entry["long_score"]  >= min_c: return "LONG"
    if d == "SHORT" and entry["short_score"] >= min_c: return "SHORT"
    return "HOLD"

# ─────────────────────────────────────────────────────────────
# POZİSYON
# ─────────────────────────────────────────────────────────────

class Position:
    def __init__(self, symbol: str):
        self.symbol         = symbol
        self.active         = False
        self.side           = None
        self.entry_price    = 0.0
        self.stop_loss      = 0.0
        self.take_profit    = 0.0
        self.trail_sl       = 0.0
        self.peak           = 0.0
        self.valley         = 0.0
        self.amount         = 0.0
        self.risk_pct       = 0.0   # |giriş - SL| / giriş → R-bazlı çıkış eşikleri için
        self.exchange_sl    = 0.0   # #2 borsada ŞU AN duran STOP seviyesi (trailing senkronu için)
        self.open_time      = None
        self.cooldown_until = None

    def open(self, side: str, price: float, atr: float, amount: float):
        cfg  = CONFIG
        cost = (cfg["commission"] + cfg["slippage"]) * 2

        if side == "LONG":
            sl_atr  = price - atr * cfg["atr_sl_mult"]
            sl_hmax = price * (1 - cfg["max_sl_pct"])
            sl_hmin = price * (1 - cfg["min_sl_pct"])
            self.stop_loss   = round(min(max(sl_atr, sl_hmax), sl_hmin), 6)
            # TP, GERÇEKLEŞEN SL mesafesinden türetilir → R:R her zaman sabit (eski formül
            # SL'i tabana sabitleyip TP'yi ATR ile küçülttüğü için düşük volde 1:1'e çöküyordu)
            sl_dist          = price - self.stop_loss
            self.take_profit = round(price + sl_dist * cfg["rr_ratio"] + price * cost, 6)
            self.trail_sl    = self.stop_loss        # başlangıçta SL ile aynı
            self.peak        = price
            self.valley      = 0.0
        else:
            sl_atr  = price + atr * cfg["atr_sl_mult"]
            sl_hmax = price * (1 + cfg["max_sl_pct"])
            sl_hmin = price * (1 + cfg["min_sl_pct"])
            self.stop_loss   = round(max(min(sl_atr, sl_hmax), sl_hmin), 6)
            sl_dist          = self.stop_loss - price
            self.take_profit = round(price - sl_dist * cfg["rr_ratio"] - price * cost, 6)
            self.trail_sl    = self.stop_loss        # başlangıçta SL ile aynı
            self.valley      = price
            self.peak        = 0.0

        self.active      = True
        self.side        = side
        self.entry_price = price
        self.open_time   = time.time()
        self.amount      = amount   # caller'dan gelen, borsa precision'ına uygun miktar
        self.risk_pct    = abs(price - self.stop_loss) / price   # 1R = bu mesafe
        self.exchange_sl = self.stop_loss   # send_open bu seviyeyi borsaya koyacak

        sl_pct = abs(price - self.stop_loss)   / price * 100
        tp_pct = abs(price - self.take_profit) / price * 100
        log.info(
            f"📈 [{self.symbol}] {side} AÇILDI\n"
            f"   Giriş : {price:,.6f}  ATR: {atr:,.6f}\n"
            f"   SL    : {self.stop_loss:,.6f}  (-%{sl_pct:.2f})\n"
            f"   TP    : {self.take_profit:,.6f}  (+%{tp_pct:.2f})\n"
            f"   R:R   : 1:{tp_pct/sl_pct:.1f}  Miktar: {self.amount:.6f}"
        )

    def update_trailing(self, price: float) -> bool:
        cfg        = CONFIG
        # R-bazlı eşikler: işlemin kendi risk mesafesine (1R) göre ölçeklenir.
        risk       = self.risk_pct if self.risk_pct > 0 else cfg["min_sl_pct"]
        min_profit = cfg["trail_start_r"]  * risk
        be_pct     = cfg["breakeven_at_r"] * risk
        base_pct   = cfg["trail_pct"]
        max_pct    = cfg["trail_max_pct"]

        if self.side == "LONG":
            profit = (price - self.entry_price) / self.entry_price
            # Breakeven
            if profit >= be_pct:
                be = round(self.entry_price * 1.0001, 6)
                if self.stop_loss < be:
                    self.stop_loss = be
                    log.info(f"🔒 [{self.symbol}] Breakeven → {be:,.6f}")
            # Trailing güncelleme — sadece kârdayken
            if profit >= min_profit:
                pct = max_pct if profit >= max_pct else base_pct
                if price > self.peak:
                    self.peak = price
                    new_sl = round(price * (1 - pct), 6)
                    # Trailing SL'i ASLA girişin altına çekme — kazananı zarara çevirmeyi önler
                    new_sl = max(new_sl, round(self.entry_price * 1.0001, 6))
                    if new_sl > self.trail_sl:
                        self.trail_sl = new_sl
                        # stop_loss'u da trail ile senkronize et — SL bypass'ı önle
                        if new_sl > self.stop_loss:
                            self.stop_loss = new_sl
                        log.info(f"📶 [{self.symbol}] Trail → {self.trail_sl:,.6f} (peak: {self.peak:,.6f})")
            # Trail SL kontrolü — trailing bir kez aktive olduysa (peak entry'den yukarı çıktıysa)
            # anlık profit'e bakmadan SL seviyesinde tetiklenir
            trailing_active = self.peak > self.entry_price
            if trailing_active:
                return price <= self.trail_sl
            return False

        else:  # SHORT
            profit = (self.entry_price - price) / self.entry_price
            if profit >= be_pct:
                be = round(self.entry_price * 0.9999, 6)
                if self.stop_loss > be:
                    self.stop_loss = be
                    log.info(f"🔒 [{self.symbol}] Breakeven → {be:,.6f}")
            if profit >= min_profit:
                pct = max_pct if profit >= max_pct else base_pct
                if price < self.valley:
                    self.valley = price
                    new_sl = round(price * (1 + pct), 6)
                    # Trailing SL'i ASLA girişin üstüne çekme — kazananı zarara çevirmeyi önler
                    new_sl = min(new_sl, round(self.entry_price * 0.9999, 6))
                    if new_sl < self.trail_sl:
                        self.trail_sl = new_sl
                        # stop_loss'u da trail ile senkronize et — SL bypass'ı önle
                        if new_sl < self.stop_loss:
                            self.stop_loss = new_sl
                        log.info(f"📶 [{self.symbol}] Trail → {self.trail_sl:,.6f} (valley: {self.valley:,.6f})")
            # Trail SL kontrolü — trailing bir kez aktive olduysa (valley entry'den aşağı düştüyse)
            # anlık profit'e bakmadan SL seviyesinde tetiklenir
            trailing_active = self.valley > 0 and self.valley < self.entry_price
            if trailing_active:
                return price >= self.trail_sl
            return False

    def check_exit(self, price: float) -> str | None:
        if not self.active:
            return None

        # ── ROI TP kontrolü (kaldıraçlı) ──────────────────────
        if CONFIG.get("roi_tp_enabled", False):
            roi_pct = CONFIG.get("roi_tp_pct", 0.035)
            if self.side == "LONG":
                profit = (price - self.entry_price) / self.entry_price * CONFIG["leverage"]
            else:
                profit = (self.entry_price - price) / self.entry_price * CONFIG["leverage"]
            if profit >= roi_pct:
                return "ROI_TP"
        # ───────────────────────────────────────────────────────

        # open_time None ise şu anı kullan — bot yeniden başlatılmış demek
        if self.open_time is None:
            self.open_time = time.time()
        if (time.time() - self.open_time) / 3600 >= CONFIG["max_pos_hours"]:
            return "ZAMAN_LIMITI"
        if self.side == "LONG":
            if price >= self.take_profit:    return "TAKE_PROFIT"
            if self.update_trailing(price):  return "TRAILING_STOP"
            if price <= self.stop_loss:      return "STOP_LOSS"
        else:
            if price <= self.take_profit:    return "TAKE_PROFIT"
            if self.update_trailing(price):  return "TRAILING_STOP"
            if price >= self.stop_loss:      return "STOP_LOSS"
        return None

    def close(self, price: float, reason: str):
        cfg     = CONFIG
        pnl_pct = (price / self.entry_price - 1) * 100 if self.side == "LONG" \
                  else (self.entry_price / price - 1) * 100
        pnl_lev = pnl_pct * cfg["leverage"]
        cost    = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * cfg["leverage"]
        pnl_net = pnl_lev - cost
        dur     = int((time.time() - self.open_time) / 60) if self.open_time else 0
        emoji   = "🟢" if pnl_net >= 0 else "🔴"

        log.info(
            f"{emoji} [{self.symbol}] KAPANDI [{reason}]\n"
            f"   Çıkış : {price:,.6f}  Süre: {dur} dk\n"
            f"   PnL   : brüt {pnl_lev:+.2f}%  net {pnl_net:+.2f}%  (maliyet: -{cost:.2f}%)"
        )
        pnl_tracker.record(pnl_net, cfg["trade_usdt"])

        cd = cfg["cooldown_sl_sec"] if reason == "STOP_LOSS" else cfg["cooldown_tp_sec"]
        log.info(f"⏸️  [{self.symbol}] Cooldown: {cd//60} dk ({reason})")

        self.active         = False
        self.side           = None
        self.entry_price    = 0.0
        self.open_time      = None
        self.cooldown_until = time.time() + cd

    def in_cooldown(self) -> bool:
        return self.cooldown_until is not None and time.time() < self.cooldown_until

# ─────────────────────────────────────────────────────────────
# EMİRLER
# ─────────────────────────────────────────────────────────────

def send_open(ex, symbol, side, amount, price, sl, tp) -> bool:
    if CONFIG["dry_run"]:
        log.info(f"[DRY RUN] {side} {symbol} {amount:.6f} @ {price:,.6f}  SL:{sl:,.6f} TP:{tp:,.6f}")
        return True
    os_ = "buy" if side == "LONG" else "sell"
    cs  = "sell" if side == "LONG" else "buy"
    try:
        ex.create_market_order(symbol, os_, amount)
    except Exception as e:
        log.error(f"❌ [{symbol}] Açılış emri BAŞARISIZ (pozisyon açılmadı): {e}")
        return False
    # Market emri başarılı oldu — pozisyon artık gerçek. SL/TP eklenmese de
    # pozisyonu hafızadan SİLME; sadece koruma eksik olarak işaretle ve devam et.
    # stopPrice borsa tick-size'ına yuvarlanmazsa Binance reddeder ve emir gözükmez.
    sl_p = _prc(ex, symbol, sl)
    tp_p = _prc(ex, symbol, tp)
    amt  = _amt(ex, symbol, amount)
    sl_ok = tp_ok = False
    try:
        ex.create_order(symbol, "STOP_MARKET", cs, amt, params={"stopPrice": sl_p, "reduceOnly": True})
        sl_ok = True
    except Exception as e:
        log.error(f"🚨 [{symbol}] SL (STOP_MARKET) emri BAŞARISIZ: {e}")
    try:
        ex.create_order(symbol, "TAKE_PROFIT_MARKET", cs, amt, params={"stopPrice": tp_p, "reduceOnly": True})
        tp_ok = True
    except Exception as e:
        log.error(f"🚨 [{symbol}] TP (TAKE_PROFIT_MARKET) emri BAŞARISIZ: {e}")

    if sl_ok and tp_ok:
        log.info(f"🛡️  [{symbol}] SL/TP borsaya kuruldu  SL:{sl_p:,.6f}  TP:{tp_p:,.6f}")
    else:
        log.error(
            f"🚨 [{symbol}] Koruma EKSİK kuruldu (SL={'✅' if sl_ok else '❌'} TP={'✅' if tp_ok else '❌'})! "
            f"Bot check_exit ile izler ama bot kapanırsa pozisyon korumasız — Binance'te manuel SL/TP koy."
        )
    return True


def cancel_open_orders(ex, symbol):
    """Sembole ait tüm açık emirleri iptal eder (STOP_MARKET ve TAKE_PROFIT_MARKET dahil)."""
    # 1. Toplu iptal dene
    try:
        ex.cancel_all_orders(symbol)
    except Exception as e:
        log.warning(f"⚠️  [{symbol}] Toplu iptal başarısız, tek tek denenecek: {e}")

    # 2. Kalan emirleri tek tek iptal et (Binance bazen STOP/TP emirlerini toplu iptalden ıskalar)
    try:
        open_orders = ex.fetch_open_orders(symbol)
        for o in open_orders:
            try:
                ex.cancel_order(o["id"], symbol)
                log.info(f"🗑️  [{symbol}] Emir iptal edildi: {o['id']} ({o.get('type','')})")
            except Exception as e:
                log.warning(f"⚠️  [{symbol}] Emir {o['id']} iptal edilemedi: {e}")
    except Exception as e:
        log.warning(f"⚠️  [{symbol}] Açık emirler listelenemedi: {e}")


def update_exchange_stop(ex, pos) -> bool:
    """#2: Trailing SL ilerleyince borsadaki STOP emrini yeni seviyeye taşır.
    Eski emirleri iptal edip STOP + TP'yi yeniden kurar. Böylece bot çökse bile
    güncel (trailing) SL borsada durur. Başarılıysa pos.exchange_sl güncellenir."""
    if CONFIG["dry_run"]:
        pos.exchange_sl = pos.stop_loss
        return True
    cs  = "sell" if pos.side == "LONG" else "buy"
    amt = _amt(ex, pos.symbol, pos.amount)
    try:
        cancel_open_orders(ex, pos.symbol)
        ex.create_order(pos.symbol, "STOP_MARKET",        cs, amt,
                        params={"stopPrice": _prc(ex, pos.symbol, pos.stop_loss),  "reduceOnly": True})
        ex.create_order(pos.symbol, "TAKE_PROFIT_MARKET", cs, amt,
                        params={"stopPrice": _prc(ex, pos.symbol, pos.take_profit), "reduceOnly": True})
        pos.exchange_sl = pos.stop_loss
        log.info(f"🔄 [{pos.symbol}] Borsa SL güncellendi → {pos.stop_loss:,.6f} (trailing senkron)")
        return True
    except Exception as e:
        log.warning(f"⚠️  [{pos.symbol}] Borsa SL güncellenemedi (bot izlemeye devam eder): {e}")
        return False


def calc_amount(ex, symbol: str, price: float):
    """Pozisyon miktarını borsa precision'ına yuvarlar ve minimum miktar/notional
    kontrolü yapar. Minimumun altındaysa None döner (→ pozisyon açma, atla).
    Sessizce minimuma şişirmez; bu, belirlenen riski (trade_usdt) bozardı."""
    cfg = CONFIG
    raw = cfg["trade_usdt"] * cfg["leverage"] / price
    if cfg["dry_run"]:
        return round(raw, 6)
    try:
        amount = float(ex.amount_to_precision(symbol, raw))
    except Exception:
        amount = round(raw, 6)
    try:
        m        = ex.market(symbol)
        min_amt  = (m.get("limits", {}).get("amount", {}) or {}).get("min")
        min_cost = (m.get("limits", {}).get("cost", {}) or {}).get("min")
    except Exception:
        min_amt = min_cost = None
    if amount <= 0:
        return None
    notional = amount * price
    if min_amt and amount < float(min_amt):
        need = float(min_amt) * price / cfg["leverage"]
        log.info(f"⏭️  [{symbol}] Miktar {amount:.6f} < borsa min {min_amt} → ATLANIYOR "
                 f"(açmak için trade_usdt ≈ {need:.1f}+ olmalı, ya da coini çıkar).")
        return None
    if min_cost and notional < float(min_cost):
        need = float(min_cost) / cfg["leverage"]
        log.info(f"⏭️  [{symbol}] Notional {notional:.1f} < borsa min {min_cost} → ATLANIYOR "
                 f"(trade_usdt ≈ {need:.1f}+ olmalı).")
        return None
    return amount


def fetch_live_positions(ex, symbols):
    """Borsadaki açık pozisyonları {symbol: contracts} olarak döner.
    Hata olursa None döner → o döngü dış-kapanış kontrolü atlanır."""
    if CONFIG["dry_run"]:
        # KRİTİK: dry run'da borsa yok → None dön (boş {} DEĞİL!).
        # Boş {} dönersek run_symbol her açık pozisyonu "borsada kapanmış" sanıp
        # bir sonraki döngüde anında kapatır; SL/TP/trailing hiç test edilmez.
        # Bu yüzden dry run "iyi" görünüyordu ama stratejiyi hiç çalıştırmıyordu.
        return None
    try:
        raw = ex.fetch_positions(symbols)
    except Exception as e:
        log.warning(f"⚠️  Canlı pozisyon okunamadı (senkron bu döngü atlanıyor): {e}")
        return None
    out = {}
    for p in raw:
        try:
            out[p.get("symbol")] = float(p.get("contracts") or 0)
        except Exception:
            pass
    return out


def fetch_exit_price(ex, symbol, fallback):
    """Borsadaki gerçek kapanış fiyatını son trade'den okur; bulamazsa fallback döner."""
    try:
        trades = ex.fetch_my_trades(symbol, limit=5)
        if trades:
            return float(trades[-1]["price"])
    except Exception:
        pass
    return fallback


def position_is_flat(ex, symbol) -> bool:
    """Borsada bu sembolde açık pozisyon yoksa True döner.
    Bilinmiyorsa (API hatası) güvenli tarafta kalmak için False döner."""
    try:
        for p in ex.fetch_positions([symbol]):
            if p.get("symbol") == symbol and abs(float(p.get("contracts") or 0)) > 1e-12:
                return False
        return True
    except Exception:
        return False


def send_close(ex, symbol, side, amount, price) -> bool:
    """Kapatma emri gönderir, başarısız olursa 3 kez dener."""
    if CONFIG["dry_run"]:
        log.info(f"[DRY RUN] KAPAT {side} {symbol} @ {price:,.6f}")
        return True

    # 1. Önce mevcut SL/TP emirlerini iptal et
    cancel_open_orders(ex, symbol)

    # 2. Market emriyle pozisyonu kapat
    cs  = "sell" if side == "LONG" else "buy"
    amt = _amt(ex, symbol, amount)
    closed = False
    for attempt in range(1, 4):
        try:
            ex.create_market_order(symbol, cs, amt, params={"reduceOnly": True})
            closed = True
            break
        except Exception as e:
            msg = str(e)
            # -2022 / ReduceOnly rejected: kapatılacak pozisyon YOK demektir.
            # Pozisyon borsada zaten kapanmış (SL/TP tetiklenmiş) → hata değil, senkronla.
            if "-2022" in msg or "ReduceOnly" in msg:
                if position_is_flat(ex, symbol):
                    log.info(f"ℹ️  [{symbol}] Pozisyon borsada zaten kapalı (SL/TP tetiklenmiş) — kapatma gereksiz, senkronlandı")
                    cancel_open_orders(ex, symbol)
                    return True
            log.error(f"❌ [{symbol}] Kapatma denemesi {attempt}/3 BAŞARISIZ: {e}")
            if attempt < 3:
                time.sleep(2)

    if not closed:
        log.error(f"🚨 [{symbol}] Kapatma TAMAMEN BAŞARISIZ oldu, pozisyon hâlâ AÇIK kalabilir — manuel kontrol et!")
        return False

    # 3. Market emri başarılı olduktan sonra tekrar kontrol et — kalan emir varsa temizle
    time.sleep(0.5)
    cancel_open_orders(ex, symbol)
    return True

# ─────────────────────────────────────────────────────────────
# RESTART MUTABAKATI
# ─────────────────────────────────────────────────────────────

def compute_sltp(price: float, atr: float, side: str):
    """SL/TP'yi Position.open ile BİREBİR aynı formülle hesaplar."""
    cfg  = CONFIG
    cost = (cfg["commission"] + cfg["slippage"]) * 2
    if side == "LONG":
        sl_atr  = price - atr * cfg["atr_sl_mult"]
        sl_hmax = price * (1 - cfg["max_sl_pct"])
        sl_hmin = price * (1 - cfg["min_sl_pct"])
        sl = round(min(max(sl_atr, sl_hmax), sl_hmin), 6)
        tp = round(price + (price - sl) * cfg["rr_ratio"] + price * cost, 6)
    else:
        sl_atr  = price + atr * cfg["atr_sl_mult"]
        sl_hmax = price * (1 + cfg["max_sl_pct"])
        sl_hmin = price * (1 + cfg["min_sl_pct"])
        sl = round(max(min(sl_atr, sl_hmax), sl_hmin), 6)
        tp = round(price - (sl - price) * cfg["rr_ratio"] - price * cost, 6)
    return sl, tp


def _amt(ex, symbol, amount):
    try:    return float(ex.amount_to_precision(symbol, amount))
    except Exception: return amount


def _prc(ex, symbol, price):
    try:    return float(ex.price_to_precision(symbol, price))
    except Exception: return price


def reconcile_positions(ex, positions: dict):
    """
    Bot başlarken borsadaki AÇIK pozisyonları okuyup yerel Position
    nesnelerine yükler. Böylece restart sonrası mevcut pozisyon yönetilir
    ve aynı coinde ÇİFT pozisyon açılmaz. SL/TP emri eksikse yeniden kurar.
    """
    if CONFIG["dry_run"]:
        return
    cfg = CONFIG
    try:
        raw = ex.fetch_positions(list(positions.keys()))
    except Exception as e:
        log.warning(f"⚠️  Mutabakat: pozisyonlar okunamadı (devam ediliyor): {e}")
        return

    found = 0
    for p in raw:
        try:
            contracts = float(p.get("contracts") or 0)
            if contracts == 0:
                continue
            sym = p.get("symbol")
            if sym not in positions:
                log.warning(f"⚠️  [{sym}] Borsada açık pozisyon var ama tarama listesinde yok — bot yönetmeyecek, manuel kontrol et!")
                continue

            side        = "LONG" if str(p.get("side", "")).lower() == "long" else "SHORT"
            entry_price = float(p.get("entryPrice") or 0)
            if entry_price <= 0:
                log.warning(f"⚠️  [{sym}] Mutabakat: giriş fiyatı okunamadı, atlanıyor")
                continue
            amount = abs(contracts)

            pos = positions[sym]
            pos.active      = True
            pos.side        = side
            pos.entry_price = entry_price
            pos.amount      = amount

            # Zaman aşımını sıfırlamamak için: gerçek zamanı almaya çalışalım, yoksa yarım süre varsayalım
            pos.open_time   = _estimate_open_time(ex, sym, side)
            pos.peak        = entry_price
            pos.valley      = entry_price

            # Borsadaki mevcut SL/TP emirlerini oku
            sl_found = tp_found = None
            try:
                orders = ex.fetch_open_orders(sym)
            except Exception as e:
                orders = []
                log.warning(f"⚠️  [{sym}] Mutabakat: açık emirler okunamadı: {e}")
            for o in orders:
                info  = o.get("info", {}) or {}
                otype = str(info.get("type") or o.get("type") or "").upper()
                stop  = info.get("stopPrice") or o.get("triggerPrice") or o.get("stopPrice")
                if stop in (None, "", 0, "0"):
                    continue
                stop = float(stop)
                if "TAKE_PROFIT" in otype:
                    tp_found = stop
                elif "STOP" in otype:
                    sl_found = stop

            if sl_found and tp_found:
                pos.stop_loss   = round(sl_found, 6)
                pos.take_profit = round(tp_found, 6)
                pos.trail_sl    = pos.stop_loss
                log.info(
                    f"🔁 [{sym}] Mevcut {side} pozisyon yüklendi  "
                    f"giriş={entry_price:,.6f} miktar={amount:.6f}  "
                    f"SL={pos.stop_loss:,.6f} TP={pos.take_profit:,.6f} (borsadan)"
                )
            else:
                # Koruma eksik → ATR'den yeniden hesapla ve emirleri yeniden kur
                try:
                    df1h = fetch_ohlcv(ex, sym, cfg["entry_tf"], limit=300)
                    e    = calc_entry(df1h)
                    atr  = e["atr"] if e else entry_price * 0.01
                except Exception:
                    atr = entry_price * 0.01
                sl, tp          = compute_sltp(entry_price, atr, side)
                pos.stop_loss   = sl
                pos.take_profit = tp
                pos.trail_sl    = sl
                log.warning(
                    f"🔁 [{sym}] {side} pozisyon yüklendi ama SL/TP EKSİKTİ → yeniden kuruldu  "
                    f"SL={sl:,.6f} TP={tp:,.6f}"
                )
                try:
                    ex.cancel_all_orders(sym)
                    cs   = "sell" if side == "LONG" else "buy"
                    a    = _amt(ex, sym, amount)
                    ex.create_order(sym, "STOP_MARKET",        cs, a, params={"stopPrice": _prc(ex, sym, sl), "reduceOnly": True})
                    ex.create_order(sym, "TAKE_PROFIT_MARKET", cs, a, params={"stopPrice": _prc(ex, sym, tp), "reduceOnly": True})
                except Exception as e:
                    log.error(f"🚨 [{sym}] Mutabakat: koruma emri yeniden kurulamadı: {e} — MANUEL kontrol et!")

            # R-bazlı çıkış eşikleri için risk mesafesini hesapla (restart sonrası da doğru çalışsın)
            if entry_price > 0:
                pos.risk_pct = abs(entry_price - pos.stop_loss) / entry_price
            pos.exchange_sl = pos.stop_loss   # #2 borsadaki güncel STOP seviyesi
            found += 1
        except Exception as e:
            log.warning(f"⚠️  Mutabakat: bir pozisyon işlenemedi: {e}")

    if found:
        log.info(f"🔁 Mutabakat tamam: {found} açık pozisyon borsadan yüklendi")
    else:
        log.info("🔁 Mutabakat: borsada açık pozisyon yok, temiz başlangıç")


def _estimate_open_time(ex, symbol: str, side: str) -> float:
    """Mevcut pozisyonun açılış zamanını bulmaya çalışır, bulamazsa zaman aşımının yarısını doldurmuş gibi döner."""
    # Gerçek zamanı almayı dene (son işlemlerden)
    try:
        trades = ex.fetch_my_trades(symbol, limit=50)
        # Pozisyon yönüne uygun, en son alım/satım işlemini bul
        wanted = "buy" if side == "LONG" else "sell"
        for trade in reversed(trades):
            if trade["side"] == wanted:
                return trade["timestamp"] / 1000  # ms -> saniye
    except Exception:
        pass
    # Bulunamazsa, bot başlangıcından itibaren max sürenin yarısı kadar açık kalmış gibi kabul et
    return time.time() - CONFIG["max_pos_hours"] * 1800  # yarısı


# ─────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────

def log_scan(sym, trend, entry, signal, pos, daily, trend_1h="NONE"):
    t   = lambda b: "✅" if b else "⬜"
    cfg = CONFIG
    # Tahmini SL% (clamp dahil) ve ona bağlı TP% — gerçek R:R'yi yansıtır
    sl_p = entry["atr"] * cfg["atr_sl_mult"] / entry["price"] * 100
    sl_p = min(max(sl_p, cfg["min_sl_pct"] * 100), cfg["max_sl_pct"] * 100)
    tp_p = sl_p * cfg["rr_ratio"]

    trail_info = ""
    if pos.active:
        if pos.side == "LONG":
            pnl = (entry["price"] / pos.entry_price - 1) * 100 * cfg["leverage"]
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Peak: {pos.peak:,.6f})\n  Anlık PnL : {pnl:+.2f}%"
        else:
            pnl = (pos.entry_price / entry["price"] - 1) * 100 * cfg["leverage"]
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Valley: {pos.valley:,.6f})\n  Anlık PnL : {pnl:+.2f}%"

    daily_ok  = daily == "NONE" or daily == trend["direction"]
    ema_ok    = (trend["direction"] == "LONG"  and trend["ema20"] > trend["ema50"]) or \
                (trend["direction"] == "SHORT" and trend["ema20"] < trend["ema50"])

    log.info(
        f"\n{'─'*54}\n"
        f"  [{sym}]\n"
        f"  1d: {'✅' if daily_ok else '⬜'} {daily}  "
        f"4h: {'📈' if trend['direction']=='LONG' else '📉' if trend['direction']=='SHORT' else '➡'} {trend['direction']}  "
        f"1h: {'📈' if trend_1h=='LONG' else '📉' if trend_1h=='SHORT' else '➡'} {trend_1h}\n"
        f"  EMA  : 20={trend['ema20']:,.4f}  50={trend['ema50']:,.4f}  200={trend['ema200']:,.4f}  {'✅' if ema_ok else '⬜'}\n"
        f"  ADX  : {trend['adx']:.1f}  {'✅ güçlü' if trend['adx_ok'] else '⬜ yatay'}\n"
        f"  Fiyat: {entry['price']:>16,.6f}   ATR: {entry['atr']:,.6f}\n"
        f"  SL±{sl_p:.2f}%  TP±{tp_p:.2f}%  R:R 1:{tp_p/sl_p:.1f}\n"
        f"  StochRSI: K={entry['sk']:.1f}  D={entry['sd']:.1f}   RSI: {entry['rsi']:.1f}\n"
        f"  MACD : {entry['macd']:.6f}  Sig: {entry['msig']:.6f}\n"
        f"  ST   : {entry['st_val']:,.6f}  {'📈' if entry['st_long'] else '📉'}\n"
        f"  Hacim: {entry['volume']:.0f}  (Ort:{entry['vol_ma']:.0f})  {t(entry['vol_ok'])}\n"
        f"  LONG ({entry['long_score']}/5, min={cfg['min_conditions']}): "
        f"StochRSI{t(entry['stoch_long'])} RSI{t(entry['rsi_long'])} MACD{t(entry['macd_up'])} Hacim{t(entry['vol_ok'])} ST{t(entry['st_long'])}\n"
        f"  SHORT({entry['short_score']}/5, min={cfg['min_conditions']}): "
        f"StochRSI{t(entry['stoch_short'])} RSI{t(entry['rsi_short'])} MACD{t(entry['macd_down'])} Hacim{t(entry['vol_ok'])} ST{t(entry['st_short'])}\n"
        f"  Sinyal: {signal}   Pozisyon: {pos.side if pos.active else 'YOK'}"
        f"{trail_info}\n"
        f"{'─'*54}"
    )

# ─────────────────────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────────────────────

def count_open(positions: dict) -> int:
    return sum(1 for p in positions.values() if p.active)


def run_symbol(ex, symbol, pos, positions, btc_chg: float = 0.0, live_pos=None, allow_entry: bool = True):
    cfg = CONFIG
    # ── 1. Anlık fiyatı al (pozisyon çıkışı için her şeyden önemli) ──
    price = fetch_current_price(ex, symbol)
    if price is None:
        log.warning(f"⚠️ [{symbol}] Anlık fiyat alınamadı, bu döngü atlanıyor")
        return

    # ── 2. Eğer açık pozisyon varsa ÇIKIŞ KONTROLÜ ÖNCE ──
    if pos.active:
        # ── Borsa-tarafı kapanış kontrolü ──
        # SL/TP emri Binance'te tetiklenip pozisyonu kapatmış olabilir; bot kaçırmasın.
        if live_pos is not None and abs(live_pos.get(symbol, 0.0)) < 1e-12:
            exit_px = fetch_exit_price(ex, symbol, price)
            try:
                cancel_open_orders(ex, symbol)   # tetiklenmeyen diğer emri temizle
            except Exception:
                pass
            if pos.side == "LONG":
                loss = exit_px < pos.entry_price
            else:
                loss = exit_px > pos.entry_price
            reason = "STOP_LOSS" if loss else "TAKE_PROFIT"
            log.warning(f"🔄 [{symbol}] Pozisyon BORSADA kapanmış ({reason} tetiklenmiş) — "
                        f"senkronize ediliyor @ {exit_px:,.6f}")
            pos.close(exit_px, reason)
            return

        # BTC dump koruması
        btc_exit = (
            cfg["btc_filter_enabled"]
            and pos.side == "LONG"
            and btc_chg <= -cfg["btc_exit_threshold"]
        )
        if btc_exit:
            log.warning(f"🚨 [{symbol}] BTC dump (%{btc_chg*100:.1f}%) → LONG kapatılıyor")
            ok = send_close(ex, symbol, pos.side, pos.amount, price)
            if ok:
                pos.close(price, "BTC_DUMP")
            return

        reason = pos.check_exit(price)
        if reason:
            ok = send_close(ex, symbol, pos.side, pos.amount, price)
            if ok:
                pos.close(price, reason)
            # Kapatma başarısız olursa pozisyonu kapatmayı denemeye devam etsin diye pos.active kalır, return
            return

        # #2: Çıkış tetiklenmedi ama trailing SL ilerlediyse borsadaki STOP'u güncelle.
        # Sadece eşik kadar oynadıysa (gereksiz cancel/create churn'ü önler).
        if cfg.get("sync_trailing_to_exchange") and pos.entry_price > 0:
            moved = abs(pos.stop_loss - pos.exchange_sl) / pos.entry_price
            if moved >= cfg["sl_sync_threshold_pct"]:
                update_exchange_stop(ex, pos)
        return   # pozisyon hâlâ açık → yeni girişe gerek yok, döngüyü hızlı tut

    # ── 2.5 Yeni giriş mümkün değilse AĞIR HESABI ATLA ──────────────
    # Pozisyon hâlâ açıksa, cooldown'daysa veya max pozisyon dolduysa yeni
    # giriş olamaz. Bu durumda 1d/4h/1h OHLCV çekmek gereksiz: hem API yükü
    # hem de döngüyü yavaşlatıp açık pozisyonların trailing/breakeven/zaman
    # çıkışını CANLIDA geciktiriyor. Erken çık.
    if pos.active:
        return
    if not allow_entry:
        return   # günlük kâr hedefi molası → yeni işlem yok (açık pozisyonlar yukarıda yönetildi)
    if pos.in_cooldown():
        mins = int((pos.cooldown_until - time.time()) / 60) + 1
        log.info(f"⏸️  [{symbol}] Cooldown: {mins} dk")
        return
    if count_open(positions) >= cfg["max_positions"]:
        return

    # ── 3. Sinyal hesaplamaları (sadece yeni giriş için gerekli) ──
    try:
        # Sinyaller SADECE KAPANMIŞ mumlarla hesaplanır. Borsa son eleman olarak
        # OLUŞMAKTA OLAN (yarım) mumu döner; onu atmazsak indikatörler her 15sn'de
        # repaint eder (hacim yarım kalır, MACD/StochRSI/SuperTrend sürekli değişir)
        # ve bot mum kapanınca yok olacak sinyallere girer. iloc[:-1] = son KAPALI mum.
        df1d = fetch_ohlcv_cached(ex, symbol, cfg["daily_tf"], 260, cfg["cache_1d_sec"]).iloc[:-1].copy()
        df4h = fetch_ohlcv_cached(ex, symbol, cfg["trend_tf"], 250, cfg["cache_4h_sec"]).iloc[:-1].copy()
        df1h = fetch_ohlcv_cached(ex, symbol, cfg["entry_tf"], 300, cfg["cache_1h_sec"]).iloc[:-1].copy()

        daily  = calc_daily_trend(df1d)
        trend  = calc_trend(df4h)
        if trend is None:
            log.warning(f"⚠️  [{symbol}] Trend verisi eksik")
            return

        entry = calc_entry(df1h)
        if entry is None:
            log.warning(f"⚠️  [{symbol}] Entry verisi eksik")
            return

        trend_1h = calc_1h_trend(df1h)
        signal   = get_signal(trend, entry, daily, btc_chg, trend_1h)

        log_scan(symbol, trend, entry, signal, pos, daily, trend_1h)

        # Yeni pozisyon açma kararı (cooldown/max pozisyon yukarıda 2.5'te elendi)
        if signal in ("LONG", "SHORT"):
            amount = calc_amount(ex, symbol, price)
            if amount is None:
                pass   # calc_amount sebebini logladı (minimum altı → atla)
            elif not spread_ok(ex, symbol, cfg["max_spread_pct"]):
                pass   # #6 spread geniş → likidite düşük, atla (sebep loglandı)
            elif not ensure_leverage(ex, symbol, cfg["leverage"]):
                pass   # kaldıraç doğrulanamadı → yanlış kaldıraç riski, AÇMA (sebep loglandı)
            else:
                pos.open(signal, price, entry["atr"], amount)
                ok = send_open(ex, symbol, signal, pos.amount, price, pos.stop_loss, pos.take_profit)
                if not ok:
                    # Emir başarısız oldu — pozisyonu hafızadan da kapat
                    log.warning(f"⚠️  [{symbol}] Emir başarısız, pozisyon hafızadan siliniyor")
                    pos.active = False
                    pos.side = None

    except ccxt.NetworkError as e:
        log.warning(f"🌐 [{symbol}] Ağ: {e}")
    except ccxt.ExchangeError as e:
        log.error(f"🏦 [{symbol}] Borsa: {e}")
    except Exception as e:
        log.exception(f"💥 [{symbol}] Hata: {e}")


def main():
    global START_BALANCE
    cfg  = CONFIG
    ex   = connect_exchange()
    START_BALANCE   = fetch_balance(ex)
    current_balance = START_BALANCE      # #5 günlük limit için CANLI bakiye (periyodik yenilenir)
    last_bal_refresh = time.time()
    last_refresh  = time.time()
    symbols = build_scan_list(ex)

    log.info("=" * 54)
    log.info("  🤖 Kripto Futures Bot v10.0")
    log.info(f"  Bakiye     : {START_BALANCE:.2f} USDT")
    if cfg["symbols"]:
        _scan_mode = "sabit liste"
    else:
        _scan_mode = f"{len(cfg.get('core_symbols', []))} ana + saatlik top {cfg['top_volatile_count']} volatil"
    log.info(f"  Coinler    : {len(symbols)} coin — {_scan_mode}  (max {cfg['max_positions']} pozisyon)")
    log.info(f"  Kaldıraç   : {cfg['leverage']}x")
    log.info(f"  SL/TP      : SL ×{cfg['atr_sl_mult']} ATR (min %{cfg['min_sl_pct']*100:.1f})  R:R 1:{cfg['rr_ratio']:.1f}")
    log.info(f"  Min Koşul  : {cfg['min_conditions']}/5 koşul + zorunlu tetik")
    log.info(f"  ADX Eşiği  : {cfg['adx_threshold']}")
    log.info(f"  Cooldown   : SL={cfg['cooldown_sl_sec']//60}dk  TP={cfg['cooldown_tp_sec']//60}dk")
    log.info(f"  Zarar Lim  : {('%'+str(cfg['daily_loss_pct'])) if cfg.get('daily_loss_enabled', False) else 'KAPALI'}")
    log.info(f"  Kâr Hedefi : +%{cfg['daily_profit_target_pct']:.0f} → {cfg['profit_pause_hours']}s mola")
    if cfg.get("roi_tp_enabled"):
        log.info(f"  ROI TP     : +%{cfg['roi_tp_pct']*100:.1f} kaldıraçlı kârda anında kapat (aktif)")
    log.info(f"  Mod        : {'🧪 DRY RUN' if cfg['dry_run'] else '💰 CANLI'}")
    log.info("=" * 54)

    positions = {}
    for sym in symbols:
        positions[sym] = Position(sym)
        setup_symbol(ex, sym, cfg["leverage"])
        time.sleep(0.2)

    # Dinamik taramada mevcut bir pozisyon, o anki tarama listesinde olmayan bir
    # coinde olabilir. Mutabakatın onu da görebilmesi için ana coinleri ekle
    # (setup_symbol gerekmez — sadece varsa yüklenip yönetilecek).
    for sym in cfg.get("core_symbols", []):
        positions.setdefault(sym, Position(sym))

    # Restart mutabakatı — borsadaki açık pozisyonları yükle (çift pozisyonu önler)
    reconcile_positions(ex, positions)

    # Tarama listesi dışında açık pozisyon bulunduysa onu da yönetime al
    held = [s for s, p in positions.items() if p.active and s not in symbols]
    if held:
        log.info(f"📌 Tarama dışı açık pozisyonlar yönetime alındı: {', '.join(held)}")
        symbols = symbols + held

    pause_until = 0.0     # günlük kâr hedefi molası bitiş zamanı
    pause_day   = None    # o gün mola verildi mi (günde 1 kez)
    while True:
        # #5 Günlük % için CANLI bakiyeyi periyodik yenile.
        if not cfg["dry_run"] and time.time() - last_bal_refresh > cfg["balance_refresh_sec"]:
            b = fetch_balance_quiet(ex)
            if b is not None:
                current_balance = b
            last_bal_refresh = time.time()

        # Günlük ZARAR limiti — varsayılan KAPALI (kullanıcı -%8 durmayı kaldırdı)
        if cfg.get("daily_loss_enabled", False) and pnl_tracker.daily_limit_hit(current_balance):
            log.warning("💤 Günlük zarar limiti → 1 saat bekleniyor...")
            time.sleep(3600)
            continue

        # Günlük KÂR hedefi → N saat YENİ İŞLEM açma (açık pozisyonlar yönetilmeye devam eder)
        if pause_day != date.today() and pnl_tracker.daily_profit_hit(current_balance, cfg["daily_profit_target_pct"]):
            pause_until = time.time() + cfg["profit_pause_hours"] * 3600
            pause_day   = date.today()
            log.info(f"🎯 Günlük +%{cfg['daily_profit_target_pct']:.0f} hedefe ulaşıldı → "
                     f"{cfg['profit_pause_hours']} saat YENİ işlem YOK (açık pozisyonlar yönetiliyor)")
        allow_entry = time.time() >= pause_until

        if not cfg["symbols"] and time.time() - last_refresh > cfg["symbol_refresh_sec"]:
            log.info("🔄 Volatil coinler yenileniyor (ana coinler sabit kalır)...")
            new_syms = build_scan_list(ex)   # ana coinler + taze volatil liste
            for s in new_syms:
                if s not in positions:
                    positions[s] = Position(s)
                    setup_symbol(ex, s, cfg["leverage"])
            # GÜVENLİK: açık pozisyonu olan bir coin yeni listede yoksa onu DÜŞÜRME —
            # yoksa bot o pozisyonu artık taramaz (trailing/breakeven/zaman çıkışı durur).
            held = [s for s, p in positions.items() if p.active and s not in new_syms]
            if held:
                log.info(f"📌 Açık pozisyonlu coinler listede tutuluyor: {', '.join(held)}")
            symbols      = list(dict.fromkeys(new_syms + held))
            last_refresh = time.time()

        # BTC korelasyon filtresi için BTC değişimini al
        btc_chg = get_btc_change(ex)
        if CONFIG["btc_filter_enabled"]:
            log.info(f"📊 BTC 1h değişim: {btc_chg*100:+.2f}%  {'🔴 LONG engel' if btc_chg <= -CONFIG['btc_drop_threshold'] else '🟢 SHORT engel' if btc_chg >= CONFIG['btc_pump_threshold'] else '✅ normal'}")

        # Borsadaki gerçek pozisyon durumunu bir kez çek (dış kapanışları yakala)
        live_pos = fetch_live_positions(ex, symbols)

        if not allow_entry:
            mins = int((pause_until - time.time()) / 60) + 1
            log.info(f"🎯 Kâr hedefi molası: {mins} dk daha yeni işlem yok (açık pozisyonlar yönetiliyor)")

        for sym in symbols:
            run_symbol(ex, sym, positions[sym], positions, btc_chg, live_pos, allow_entry)
            time.sleep(0.5)

        open_c = count_open(positions)
        wr = pnl_tracker.wins / pnl_tracker.total * 100 if pnl_tracker.total else 0
        log.info(
            f"⏳ {cfg['loop_sec']}s bekleniyor...  "
            f"[Açık: {open_c}/{cfg['max_positions']}  "
            f"Oturum: {pnl_tracker.session_pnl:+.2f} USDT  "
            f"Günlük: {pnl_tracker.daily_pnl:+.2f} USDT  "
            f"WR: %{wr:.0f} ({pnl_tracker.wins}W/{pnl_tracker.losses}L)]\n"
        )
        time.sleep(cfg["loop_sec"])


if __name__ == "__main__":
    main()