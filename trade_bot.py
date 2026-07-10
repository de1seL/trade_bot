"""
╔══════════════════════════════════════════════════════════════╗
║   🤖 Kripto Futures Bot v10.0  — EMA9 EKLENDİ              ║
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

  KATMAN 4 — GİRİŞ (1 saat, min koşul + ZORUNLU taze tetik)
    Skor koşulları (6): StochRSI dönüş, RSI momentum, MACD crossover,
                        Hacim artışı, Süper Trend yönü, EMA9/20/50 hizalama
    Tetik (≥1 şart): MACD crossover VEYA StochRSI dönüşü
    Tüm sinyaller KAPANMIŞ mumdan hesaplanır (repaint yok)

── ÇIKIŞ ────────────────────────────────────────────────────────
  SL      : ATR × 1.3  (min %1.2, max %3.0)
  TP      : giriş ± (gerçek SL mesafesi × 1.5)  → R:R 1:1.5
  ROI TP  : +%3.5 kaldıraçlı kâr → direkt kapat (kapalı)
  Breakeven: +1R kârda SL → giriş fiyatına (R-bazlı)
  Trailing: +1R kârda devreye girer, %1.2 band, asla girişin altına inmez
  Zaman   : 4 saat içinde kapanmazsa çık

── KORUMALAR ─────────────────────────────────────────────────────
  • Günlük %8 zarar limiti (kapalı)
  • SL sonrası 1 saat cooldown
  • TP sonrası 1 saat cooldown
  • Max 2 eşzamanlı pozisyon
  • NaN koruması (tüm indikatörler)
  • Komisyon + slippage dahil PnL
"""

import os
import csv
import time
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor

import ccxt
import numpy as np
import pandas as pd
import ta
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────────
# AYARLAR
# ─────────────────────────────────────────────────────────────

CONFIG = {
    # ── Coinler ─────────────────────────────────────────────
    "symbols"             : [],
    "core_symbols"        : [
        "BTC/USDT:USDT",  "ETH/USDT:USDT",  "BNB/USDT:USDT",
        "SOL/USDT:USDT",  "XRP/USDT:USDT",  "DOGE/USDT:USDT",
        "ADA/USDT:USDT",  "AVAX/USDT:USDT", "LINK/USDT:USDT",
        "DOT/USDT:USDT",
    ],
    "top_volatile_count"  : 65,           # en volatil/likit ilk 65 coin (+ core = ~75) — kalite/hız dengesi
    "symbol_refresh_sec"  : 900,          # coin listesini 15 dk'da bir yenile (paralel)

    # ── Tarama filtreleri ───────────────────────────────────
    "exclude_bases"       : ["BTC", "BNB"],
    "min_volatility_pct"  : 4.0,
    "min_listing_days"    : 45,

    # ── Kaldıraç ────────────────────────────────────────────
    "leverage"            : 10,

    # ── Zaman dilimleri ─────────────────────────────────────
    "daily_tf"            : "1d",
    "trend_tf"            : "4h",
    "entry_tf"            : "1h",           # 1 saat — en az gürültü, sıkı trend-takibi için en uygun

    # ── Trend (4h) ───────────────────────────────────────────
    "ema_trend"           : 200,
    "ema_fast"            : 20,
    "ema_slow"            : 50,

    # ── ADX (4h) ─────────────────────────────────────────────
    "adx_period"          : 14,
    "adx_threshold"       : 27,             # 30 çok yüksekti; 27 = güçlü trend ama fazla kısıtlamaz
    "adx_max"             : 40,             # ADX bunun ÜSTÜNDEyse trend YORGUN → giriş yok. Veri: ADX 30-40 kârlı, 40+ kanıyor.

    # ── Günlük coin yasağı ───────────────────────────────────
    "daily_coin_ban_sl"   : 2,              # bir coin günde bu kadar SL yerse o gün TAMAMEN yasak (tekrar-deneme freni)

    # ── Stochastic RSI (entry_tf) ────────────────────────────
    "stoch_period"        : 14,
    "stoch_smooth_k"      : 3,
    "stoch_smooth_d"      : 3,
    "stoch_oversold"      : 40,
    "stoch_overbought"    : 60,

    # ── RSI (entry_tf) ───────────────────────────────────────
    "rsi_period"          : 14,
    "rsi_oversold"        : 45,
    "rsi_overbought"      : 55,

    # ── MACD (entry_tf) ──────────────────────────────────────
    "macd_fast"           : 12,
    "macd_slow"           : 26,
    "macd_sig"            : 9,
    "macd_lookback"       : 5,
    # Veri analizi: MACD crossover TRUE iken WR %30, FALSE iken %56 → MACD geç
    # sinyal, tepeden alım yaptırıyor. Tetikten ve skordan çıkarıldı.
    # (Geri açmak için ikisini True yap.)
    "macd_in_trigger"     : False,          # MACD zorunlu tetiğe dahil mi
    "macd_in_score"       : False,          # MACD skora dahil mi

    # ── Süper Trend (entry_tf) ──────────────────────────────
    "st_period"           : 10,
    "st_mult"             : 3.0,

    # ── Hacim (entry_tf) ─────────────────────────────────────
    "vol_period"          : 20,
    "vol_mult"            : 1.0,
    # Para akışı: skordaki zayıf "hacim büyüklüğü" koşulu yerine CMF (yönlü
    # alım/satım baskısı) kullan. Farklı bilgi ailesi → set decorrelate olur.
    # (Eski hacim koşuluna dönmek için use_cmf=False.)
    "use_cmf"             : True,
    "cmf_period"          : 20,
    # ── Decorrelated set: her koşul FARKLI aileden ──────────
    # Skor = RSI(momentum) + CMF(para akışı) + SuperTrend(trend) + Donchian(yapı).
    # StochRSI skordan çıkarıldı (RSI ile aynı aile = momentum tekrarı).
    # Tetik = Donchian kırılımı VEYA RSI 50 orta çizgi geçişi (taze olay).
    "use_donchian"        : True,          # Donchian kırılımı skora + tetiğe (yapı ailesi)
    "donchian_period"     : 14,            # önceki kaç mumun zirvesi/dibi kırılsın (kısa=sık kırılım)
    "stochrsi_in_score"   : False,         # StochRSI skorda mı (False = momentum tekrarını kaldır)
    "stochrsi_in_trigger" : True,          # StochRSI dönüşü TETİĞE dahil (skora değil) → yeterli tetik frekansı

    # ── Bollinger Bands (entry_tf) — AŞIRI-UZAMA FİLTRESİ ──
    "bb_period"           : 20,
    "bb_std"              : 2.0,
    "bb_filter_enabled"   : True,
    "bb_ext_frac"         : 0.0,

    # ── EMA9/20/50 Hizalama (entry_tf) ──────────────────────
    "ema9_period"         : 9,
    "ema20_period"        : 20,
    "ema50_period"        : 50,

    # ── Alt zaman dilimi teyidi (5m + 15m) ──────────────────
    # 1h yönü ile 5m VE 15m'in İKİSİ birden ters ise giriş yapma (düşen bıçak koruması).
    "ltf_confirm_enabled" : True,
    "ltf_ema_fast"        : 9,             # 5m/15m kısa-vade yönü: EMA9 vs EMA21
    "ltf_ema_slow"        : 21,

    # ── ATR & SL/TP (entry_tf) ──────────────────────────────
    "atr_period"          : 14,
    "atr_sl_mult"         : 1.3,
    "rr_ratio"            : 1.5,
    "min_sl_pct"          : 0.012,
    "max_sl_pct"          : 0.030,

    # ── Trailing & Breakeven (R-bazlı) ───────────────────────
    "breakeven_at_r"      : 1.0,
    "trail_start_r"       : 1.0,
    "trail_pct"           : 0.012,
    "trail_max_pct"       : 0.025,

    # ── Kısmi kâr-al (partial TP) ────────────────────────────
    # +1R'de pozisyonun YARISINI kapat, stop'u başabaşa çek, kalan yarı
    # uzak hedefe (runner_rr) koşsun. Kazançları büyütür, riski kilitler.
    "partial_tp_enabled"  : True,
    "partial_tp_r"        : 1.0,          # kaçıncı R'de kısmi al (1R)
    "partial_tp_frac"     : 0.5,          # ne kadarını kapat (yarısı)
    "partial_runner_rr"   : 3.0,          # kalan yarının hedefi (R cinsinden, eski 1.5 yerine)

    # ── Giriş eşiği ─────────────────────────────────────────
    "min_conditions"      : 2,    # 4 BAĞIMSIZ koşuldan en az 2 (+ zorunlu tetik). Bağımsız
                                   # set nadiren hizalandığı için 2 ≈ eski korele 3. 1h ters ise +1.
    "require_trigger"     : True,

    # ── Risk ─────────────────────────────────────────────────
    "trade_usdt"          : 10,          # (risk_based_sizing KAPALIYKEN kullanılır)
    "max_positions"       : 2,
    # Korelasyon koruması: aynı YÖNDE en fazla kaç pozisyon. 1 → en fazla 1 LONG + 1 SHORT
    # (2 alt coin aynı yönde = aslında tek büyük bahis; BTC dönerse ikisi birden batar).
    "max_per_direction"   : 1,
    # ── Para yönetimi (DİNAMİK) ──────────────────────────────
    # dynamic_leverage AÇIK → her pozisyon marjı = bakiyenin %position_pct'i;
    # kaldıraç risk hesabına göre [min,max] aralığında otomatik belirlenir.
    "dynamic_leverage"    : True,
    "position_pct"        : 0.20,         # her pozisyon marjı = bakiyenin %20'si
    "total_exposure_pct"  : 0.40,         # tüm açık pozisyonların marjı ≤ bakiyenin %40'ı
    "risk_per_trade_pct"  : 2.0,          # hedef risk: SL vurursa ~bakiyenin %2'si
    "min_leverage"        : 5,            # kaldıraç alt sınırı
    "max_leverage"        : 20,           # kaldıraç üst sınırı
    "risk_based_sizing"   : False,        # eski mod (dynamic_leverage KAPALIYKEN)
    # #2 Üst üste zarar freni: N zarar arka arkaya → M saat yeni işlem yok (whipsaw kesici)
    "consec_loss_limit"   : 3,
    "consec_loss_pause_hours": 2,
    "daily_loss_enabled"  : True,         # günlük zarar freni AÇIK
    "daily_loss_pct"      : 15.0,         # günlük -%15'e ulaşınca dur (1 saat)
    "daily_profit_target_pct": 50.0,     # günlük +%50 kâra ulaşınca 12 saat mola
    "profit_pause_hours"     : 12,
    "balance_refresh_sec" : 300,
    "cooldown_sl_sec"     : 3600,
    "cooldown_tp_sec"     : 3600,
    "max_pos_hours"       : 4,
    "max_spread_pct"      : 0.0015,

    # ── Trailing senkron ─────────────────────────────────────
    "sync_trailing_to_exchange": True,
    "sl_sync_threshold_pct"    : 0.003,

    # ── OHLCV cache ──────────────────────────────────────────
    "cache_1d_sec"        : 3600,
    "cache_4h_sec"        : 900,
    "cache_1h_sec"        : 60,           # entry_tf (1h) için cache

    # ── Komisyon ─────────────────────────────────────────────
    "commission"          : 0.0004,
    "slippage"            : 0.0002,

    # ── BTC Korelasyon Filtresi ──────────────────────────────
    "btc_filter_enabled"  : True,
    "btc_drop_threshold"  : 0.01,
    "btc_pump_threshold"  : 0.01,
    "btc_exit_threshold"  : 0.02,

    # ── ROI TP ────────────────────────────────────────────────
    "roi_tp_enabled"      : False,
    "roi_tp_pct"          : 0.035,

    # ── Zaman + Kâr çıkışı ───────────────────────────────────
    # Pozisyon N saattir açıksa VE kaldıraçlı ROI ≥ %X ise direkt kapat (kârı kilitle).
    "time_profit_enabled" : True,
    "time_profit_hours"   : 2.0,          # 2 saattir açıksa
    "time_profit_roi_pct" : 10.0,         # ve ROI ≥ +%10 ise → sat (küçük kazananları kesmesin, koşsun)

    # ── İşlem günlüğü & Bildirim ─────────────────────────────
    "trade_log_csv"       : "trades.csv",  # her kapanan işlem buraya yazılır (Excel'de aç)
    "notify_telegram"     : True,          # aç/kapa/hata/mola bildirimi (.env'de token gerekli)

    # ── Sistem ───────────────────────────────────────────────
    # Paralel tarama: aday coinlerin mumlarını 5 thread ile aynı anda çekip cache'i
    # ısıtır → döngü çok daha hızlı. SADECE veri çekme paralel; emirler yine SIRALI.
    "parallel_scan"       : True,
    "scan_workers"        : 8,            # 100 coin taranırken paralel veri çekmeyi hızlı tut
    "loop_sec"            : 15,
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
# TELEGRAM BİLDİRİM & İŞLEM GÜNLÜĞÜ
# ─────────────────────────────────────────────────────────────

def notify(text: str):
    """Telegram'a bildirim gönderir (token yoksa ya da kapalıysa sessizce geçer)."""
    if not CONFIG.get("notify_telegram") or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": "true",
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except Exception as e:
        log.warning(f"⚠️  Telegram bildirimi gönderilemedi: {e}")


_TRADE_LOG_FIELDS = [
    "time", "symbol", "side", "entry", "exit", "pnl_net_pct", "pnl_usdt",
    "reason", "dur_min", "leverage",
    "adx", "daily", "tf1h", "tf5", "tf15",
    "score", "stoch", "rsi", "macd", "vol", "st", "ema",
]

def write_trade_log(row: dict):
    """Kapanan bir işlemi trades.csv'ye ekler (yoksa başlık satırıyla oluşturur)."""
    path = CONFIG.get("trade_log_csv")
    if not path:
        return
    try:
        exists = os.path.isfile(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_TRADE_LOG_FIELDS)
            if not exists:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in _TRADE_LOG_FIELDS})
    except Exception as e:
        log.warning(f"⚠️  İşlem günlüğü yazılamadı: {e}")

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
        self.consecutive_losses = 0   # #2 üst üste zarar sayacı (kazançta sıfırlanır)
        self.daily_sl_count = {}      # {symbol: o gün kaç kez SL} → günlük coin yasağı

    def _roll_day_if_needed(self):
        if date.today() != self.daily_date:
            self.daily_pnl  = 0.0
            self.daily_date = date.today()
            self.daily_sl_count = {}   # yeni gün → yasaklar sıfırlanır

    def register_sl(self, symbol: str):
        """Bir coin STOP_LOSS yediğinde çağrılır → günlük SL sayacını artırır."""
        self._roll_day_if_needed()
        self.daily_sl_count[symbol] = self.daily_sl_count.get(symbol, 0) + 1

    def is_coin_banned(self, symbol: str) -> bool:
        """Coin bugün ban_sl kadar SL yediyse o gün yasaklı (True)."""
        self._roll_day_if_needed()
        limit = CONFIG.get("daily_coin_ban_sl", 0)
        return limit > 0 and self.daily_sl_count.get(symbol, 0) >= limit

    def record(self, pnl_pct: float, usdt: float):
        pnl_usdt = usdt * pnl_pct / 100
        self.session_pnl += pnl_usdt
        self.total       += 1
        self._roll_day_if_needed()
        self.daily_pnl += pnl_usdt
        if pnl_pct >= 0:
            self.wins += 1
            self.consecutive_losses = 0        # kazanç → seriyi sıfırla
        else:
            self.losses += 1
            self.consecutive_losses += 1        # zarar → seriyi artır
        wr = self.wins / self.total * 100 if self.total else 0
        log.info(
            f"📊 PNL | Oturum: {self.session_pnl:+.2f} USDT  "
            f"Günlük: {self.daily_pnl:+.2f} USDT  "
            f"Win Rate: %{wr:.0f} ({self.wins}W/{self.losses}L)"
        )

    def daily_limit_hit(self, balance: float) -> bool:
        self._roll_day_if_needed()
        if balance <= 0:
            return False
        if self.daily_pnl < 0 and abs(self.daily_pnl) / balance * 100 >= CONFIG["daily_loss_pct"]:
            log.warning(f"🛑 Günlük zarar limiti → 1 saat duruyor")
            return True
        return False

    def daily_profit_hit(self, balance: float, target_pct: float) -> bool:
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
        try:
            ex.load_markets()
        except Exception as e:
            log.warning(f"⚠️  Marketler şimdi yüklenemedi (sonra lazy yüklenecek): {e}")
        try:
            ex.set_position_mode(False)
            log.info("✅ Pozisyon modu: one-way")
        except Exception as e:
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
        usdt = b["USDT"]
        # Pozisyon boyutlandırması ve %40 maruziyet tavanı için SABİT toplam
        # özkaynağı (total) kullan. "free" bakiye ilk pozisyon marjı kilitlenince
        # küçülür → yanlışlıkla "maruziyet %40 dolu" der. "total" = cüzdan değeri.
        u = float(usdt.get("total") or usdt.get("free") or 0)
        free = float(usdt.get("free") or 0)
        log.info(f"💰 Bakiye: {u:.2f} USDT (toplam)  |  kullanılabilir: {free:.2f}")
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
        if "4046" not in str(e) and "No need" not in str(e):
            log.warning(f"⚠️  {symbol} margin modu: {e}")


def ensure_leverage(ex: ccxt.Exchange, symbol: str, leverage: int) -> bool:
    if CONFIG["dry_run"]:
        return True
    try:
        ex.set_leverage(leverage, symbol)
        return True
    except Exception as e:
        msg = str(e)
        if "no need" in msg.lower() or "-4046" in msg:
            return True
        log.error(f"🚫 [{symbol}] Kaldıraç {leverage}x doğrulanamadı → pozisyon AÇILMAYACAK: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# SEMBOL SEÇİCİ
# ─────────────────────────────────────────────────────────────

STABLE   = {"USDT","BUSD","USDC","DAI","TUSD","FDUSD","USDP","UST"}
FALLBACK = ["SOL/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT"]

# Binance TradFi-Perps (tokenize HİSSE/ETF) — KRİPTO DEĞİL. V-toparlar/gap yapar,
# bu trend-takip stratejisi için uygun değil (dip'te short'a yakalanılır) ve
# sözleşme (agreement) ister. Taramadan tamamen çıkarılır.
STOCK_BASES = {
    "AMD","SNDK","EWY","AAPL","TSLA","NVDA","MSFT","GOOGL","GOOG","AMZN","META",
    "COIN","MSTR","HOOD","PLTR","SMCI","NFLX","INTC","MU","QCOM","CRCL","NU","AVGO",
    "ORCL","BABA","DIS","BA","JPM","MARA","RIOT","SPY","QQQ","GLD","NKE","PYPL",
    "UBER","ABNB","SHOP","SOFI","GME","AMC","F","T","KO","PEP","WMT","COST",
}

def _is_stock_perp(m: dict) -> bool:
    """Tokenize hisse / TradFi-Perp mi? (kripto değil → taramadan çıkar)"""
    ut = str((m.get("info") or {}).get("underlyingType", "")).upper()
    if ut and ut != "COIN":              # kripto = COIN; hisse/endeks != COIN
        return True
    return str(m.get("base", "")).upper() in STOCK_BASES


def _listed_long_enough(m: dict, now_ms: int, min_age_ms: int) -> bool:
    if min_age_ms <= 0:
        return True
    ob = (m.get("info") or {}).get("onboardDate")
    try:
        return ob is None or (now_ms - int(ob)) >= min_age_ms
    except Exception:
        return True


def filter_min_leverage(ex, symbols: list[str], min_lev: int) -> list[str]:
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
        and m.get("base") not in exclude
        and not _is_stock_perp(m)                        # tokenize hisse/ETF'leri ele
        and _listed_long_enough(m, now_ms, min_age_ms)
    }

    min_vol_pct = CONFIG.get("min_volatility_pct", 0.0)
    rows = []
    for sym, t in tickers.items():
        if sym not in valid:
            continue
        vol  = t.get("quoteVolume") or 0
        spct = t.get("percentage") or 0
        pct  = abs(spct)
        if vol < 10_000_000:
            continue
        if pct < min_vol_pct:
            continue
        rows.append({"symbol": sym, "pct": pct, "spct": spct, "vol_m": vol / 1e6, "score": pct * vol})

    if not rows:
        return FALLBACK

    df = pd.DataFrame(rows).sort_values("score", ascending=False)
    # Coin en az kaldıraç tabanımızı desteklemeli (dinamik modda min_leverage)
    _need_lev = CONFIG.get("min_leverage", CONFIG["leverage"]) if CONFIG.get("dynamic_leverage") else CONFIG["leverage"]
    ranked = filter_min_leverage(ex, df["symbol"].tolist(), _need_lev)
    df = df[df["symbol"].isin(ranked)]
    df = df.sort_values("score", ascending=False).head(top_n)
    if df.empty:
        return FALLBACK

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
    cfg = CONFIG
    if cfg["symbols"]:
        return list(dict.fromkeys(cfg["symbols"]))
    core = list(cfg.get("core_symbols", []))
    dyn  = get_symbols(ex, cfg["top_volatile_count"])
    merged = list(dict.fromkeys(core + dyn))
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


def prefetch_ohlcv(ex, symbols: list):
    """Aday coinlerin TÜM zaman dilimi mumlarını 5 thread ile PARALEL çekip cache'i
    ısıtır. Read-only → güvenli (emir yok, state değişmez). Sonraki sıralı döngü
    cache'ten okuduğu için çok hızlanır. Sadece VERİ çekme paralel; emirler sıralı."""
    if not symbols:
        return
    cfg  = CONFIG
    jobs = []
    for s in symbols:
        jobs.append((s, cfg["daily_tf"], 260, cfg["cache_1d_sec"]))
        jobs.append((s, cfg["trend_tf"], 250, cfg["cache_4h_sec"]))
        jobs.append((s, cfg["entry_tf"], 300, cfg["cache_1h_sec"]))
        jobs.append((s, "5m",  120, 60))
        jobs.append((s, "15m", 120, 120))
    def _one(j):
        try:
            fetch_ohlcv_cached(ex, j[0], j[1], j[2], j[3])
        except Exception:
            pass
    try:
        with ThreadPoolExecutor(max_workers=cfg.get("scan_workers", 5)) as pool:
            list(pool.map(_one, jobs))
    except Exception as e:
        log.warning(f"⚠️  Paralel tarama hatası (sıralı devam): {e}")


def prefetch_ohlcv(ex, symbols: list[str]):
    """Aday coinlerin TÜM zaman dilimi mumlarını 5 thread ile PARALEL çekip cache'i
    ısıtır. Read-only (state değiştirmez) → güvenli. Sonraki sıralı döngü cache'ten
    okuduğu için çok hızlı çalışır. Emir/pozisyon mantığı hiç değişmez, sıralı kalır."""
    cfg = CONFIG
    if not symbols or not cfg.get("parallel_scan"):
        return
    jobs = []
    for s in symbols:
        jobs.append((s, cfg["daily_tf"], 260, cfg["cache_1d_sec"]))
        jobs.append((s, cfg["trend_tf"], 250, cfg["cache_4h_sec"]))
        jobs.append((s, cfg["entry_tf"], 300, cfg["cache_1h_sec"]))
        jobs.append((s, "5m",  120, 60))
        jobs.append((s, "15m", 120, 120))

    def _one(j):
        try:
            fetch_ohlcv_cached(ex, j[0], j[1], j[2], j[3])
        except Exception:
            pass   # bir coin patlarsa diğerleri devam etsin (sıralı döngü zaten yeniden dener)

    try:
        with ThreadPoolExecutor(max_workers=cfg.get("scan_workers", 5)) as pool:
            list(pool.map(_one, jobs))
    except Exception as e:
        log.warning(f"⚠️  Paralel ön-tarama hatası (sıralıya düşülüyor): {e}")


def get_btc_change(ex: ccxt.Exchange) -> float:
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
    try:
        return float(ex.fetch_ticker(symbol)["last"])
    except Exception:
        return None


def spread_ok(ex, symbol, max_spread: float) -> bool:
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
    if CONFIG["dry_run"]:
        return None
    try:
        b = ex.fetch_balance()
        usdt = b["USDT"]
        return float(usdt.get("total") or usdt.get("free") or 0)
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
    cfg = CONFIG
    c   = df["close"]

    if len(df) < cfg["ema_trend"] + cfg["adx_period"]:
        return None

    ema200 = ta.trend.EMAIndicator(c, window=cfg["ema_trend"]).ema_indicator()
    ema20  = ta.trend.EMAIndicator(c, window=cfg["ema_fast"]).ema_indicator()
    ema50  = ta.trend.EMAIndicator(c, window=cfg["ema_slow"]).ema_indicator()
    adx    = ta.trend.ADXIndicator(df["high"], df["low"], c, window=cfg["adx_period"]).adx()

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
    cfg = CONFIG

    if len(df) < max(cfg["stoch_period"], cfg["rsi_period"], cfg["macd_slow"],
                     cfg["atr_period"], cfg["vol_period"], cfg["ema50_period"]) + 5:
        return None

    # ── EMA9,20,50 ───────────────────────────────────────────
    ema9  = ta.trend.EMAIndicator(df["close"], window=cfg["ema9_period"]).ema_indicator()
    ema20 = ta.trend.EMAIndicator(df["close"], window=cfg["ema20_period"]).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df["close"], window=cfg["ema50_period"]).ema_indicator()
    # NaN kontrolü
    if pd.isna(ema9.iloc[-1]) or pd.isna(ema20.iloc[-1]) or pd.isna(ema50.iloc[-1]):
        return None

    # Hizalama ve kesişim bilgileri
    ema9_gt_20   = float(ema9.iloc[-1]) > float(ema20.iloc[-1])
    ema20_gt_50  = float(ema20.iloc[-1]) > float(ema50.iloc[-1])
    ema9_lt_20   = float(ema9.iloc[-1]) < float(ema20.iloc[-1])
    ema20_lt_50  = float(ema20.iloc[-1]) < float(ema50.iloc[-1])

    # Uzun için: EMA9 > EMA20 > EMA50 (üçlü hizalama)
    ema_long_ok  = ema9_gt_20 and ema20_gt_50
    # Kısa için: EMA9 < EMA20 < EMA50
    ema_short_ok = ema9_lt_20 and ema20_lt_50

    # ── StochRSI ─────────────────────────────────────────────
    stoch = ta.momentum.StochRSIIndicator(
        df["close"], window=cfg["stoch_period"],
        smooth1=cfg["stoch_smooth_k"], smooth2=cfg["stoch_smooth_d"]
    )
    df["sk"] = stoch.stochrsi_k() * 100
    df["sd"] = stoch.stochrsi_d() * 100

    # ── RSI ──────────────────────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(
        df["close"], window=cfg["rsi_period"]
    ).rsi()

    # ── MACD ─────────────────────────────────────────────────
    macd_obj = ta.trend.MACD(df["close"], window_slow=cfg["macd_slow"], window_fast=cfg["macd_fast"], window_sign=cfg["macd_sig"])
    df["macd"]  = macd_obj.macd()
    df["msig"]  = macd_obj.macd_signal()

    # ── Süper Trend ──────────────────────────────────────────
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

    # ── ATR & Hacim ──────────────────────────────────────────
    df["atr"]   = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=cfg["atr_period"]
    ).average_true_range()
    df["vol_ma"] = df["volume"].rolling(cfg["vol_period"]).mean()

    # ── Bollinger Bands ──────────────────────────────────────
    bb = ta.volatility.BollingerBands(df["close"], window=cfg["bb_period"], window_dev=cfg["bb_std"])
    df["bb_up"]  = bb.bollinger_hband()
    df["bb_lo"]  = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()

    # ── CMF (Chaikin Money Flow) — yönlü para akışı ──────────
    if cfg.get("use_cmf", True):
        df["cmf"] = ta.volume.ChaikinMoneyFlowIndicator(
            df["high"], df["low"], df["close"], df["volume"], window=cfg["cmf_period"]
        ).chaikin_money_flow()
    else:
        df["cmf"] = 0.0

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    price = float(last["close"])
    coin_chg_1h = (price - float(prev["close"])) / float(prev["close"])

    # NaN kontrolü
    _need = ["sk","sd","macd","msig","st","atr","vol_ma","rsi","bb_up","bb_lo"]
    if cfg.get("use_cmf", True):
        _need.append("cmf")
    for col in _need:
        if pd.isna(last[col]):
            return None

    # ── MACD Crossover ───────────────────────────────────────
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
    stoch_series = df["sk"].dropna()
    sk_rising  = len(stoch_series) >= 3 and float(stoch_series.iloc[-1]) > float(stoch_series.iloc[-3])
    sk_falling = len(stoch_series) >= 3 and float(stoch_series.iloc[-1]) < float(stoch_series.iloc[-3])
    stoch_long  = sk > cfg["stoch_oversold"]  and sk > sd2 and sk_rising
    stoch_short = sk < cfg["stoch_overbought"] and sk < sd2 and sk_falling

    rsi_val   = float(last["rsi"])
    rsi_series  = df["rsi"].dropna()
    rsi_rising  = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) > float(rsi_series.iloc[-3])
    rsi_falling = len(rsi_series) >= 3 and float(rsi_series.iloc[-1]) < float(rsi_series.iloc[-3])
    rsi_long  = rsi_val > cfg["rsi_oversold"]   and rsi_rising
    rsi_short = rsi_val < cfg["rsi_overbought"] and rsi_falling

    st_long  = int(last["std"]) == 1
    st_short = int(last["std"]) == -1
    vol_ok   = float(last["volume"]) > float(last["vol_ma"]) * cfg["vol_mult"]

    # CMF: yönlü para akışı (skorda hacim yerine bu kullanılır)
    cmf_val   = float(last["cmf"])
    cmf_long  = cmf_val > 0
    cmf_short = cmf_val < 0
    # Skorda "para akışı" slotu: CMF açıksa yön, değilse eski hacim büyüklüğü
    flow_long  = cmf_long  if cfg.get("use_cmf", True) else vol_ok
    flow_short = cmf_short if cfg.get("use_cmf", True) else vol_ok

    # Bollinger aşırı-uzama
    bb_up_lvl = float(last["bb_up"]); bb_lo_lvl = float(last["bb_lo"])
    _band = bb_up_lvl - bb_lo_lvl
    bb_over_long  = price > bb_up_lvl + cfg["bb_ext_frac"] * _band
    bb_over_short = price < bb_lo_lvl - cfg["bb_ext_frac"] * _band

    # ── Donchian breakout (yapı/kırılım ailesi) ──────────────
    # Fiyat ÖNCEKİ N mumun zirvesini/dibini kırdı mı → taze yapısal olay.
    donch_long = donch_short = False
    dc_up = dc_dn = 0.0
    if cfg.get("use_donchian", False):
        dp = cfg["donchian_period"]
        if len(df) >= dp + 1:
            dc_up = float(df["high"].iloc[-(dp+1):-1].max())
            dc_dn = float(df["low"].iloc[-(dp+1):-1].min())
            donch_long  = price > dc_up
            donch_short = price < dc_dn

    # ── RSI 50 orta çizgi geçişi (taze momentum olayı — tetik) ─
    rsi_cross_up = rsi_cross_dn = False
    if len(rsi_series) >= 2:
        _wr = rsi_series.iloc[-(lb+1):]
        for i in range(len(_wr) - 1):
            a = float(_wr.iloc[i]); b = float(_wr.iloc[i+1])
            if a <= 50 < b: rsi_cross_up = True
            if a >= 50 > b: rsi_cross_dn = True

    # ── Skor: bağımsız (decorrelated) aileler — config ile ───
    # Çekirdek 3 aile: RSI(momentum) + CMF/flow(para akışı) + SuperTrend(trend).
    # EMA9/20/50 SKORDA DEĞİL (calc_entry_trend'de kapı). Aşağıdakiler config'e bağlı:
    _parts_l = [rsi_long,  flow_long,  st_long]
    _parts_s = [rsi_short, flow_short, st_short]
    if cfg.get("stochrsi_in_score", True):          # StochRSI (RSI ile aynı aile — varsayılan KAPALI)
        _parts_l.append(stoch_long);  _parts_s.append(stoch_short)
    if cfg.get("macd_in_score", True):              # MACD (veri: zarar — varsayılan KAPALI)
        _parts_l.append(macd_up);     _parts_s.append(macd_down)
    if cfg.get("use_donchian", False):              # Donchian kırılımı (yapı ailesi — YENİ)
        _parts_l.append(donch_long);  _parts_s.append(donch_short)
    long_score  = sum(_parts_l)
    short_score = sum(_parts_s)
    max_score   = len(_parts_l)

    # ── Tetik (taze olay) ────────────────────────────────────
    if cfg.get("use_donchian", False):
        # Decorrelated set: Donchian kırılımı VEYA RSI 50 geçişi VEYA StochRSI dönüşü.
        # StochRSI SADECE tetik (zamanlama) — skorda yok, o yüzden skor bağımsız kalır.
        _st_l = stoch_long  if cfg.get("stochrsi_in_trigger", False) else False
        _st_s = stoch_short if cfg.get("stochrsi_in_trigger", False) else False
        long_trigger  = donch_long  or rsi_cross_up or _st_l
        short_trigger = donch_short or rsi_cross_dn or _st_s
    elif cfg.get("macd_in_trigger", True):
        long_trigger  = macd_up   or stoch_long
        short_trigger = macd_down or stoch_short
    else:
        long_trigger  = stoch_long
        short_trigger = stoch_short

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
        "cmf"         : round(cmf_val, 4),
        "cmf_long"    : cmf_long,
        "cmf_short"   : cmf_short,
        "donch_long"  : donch_long,
        "donch_short" : donch_short,
        "dc_up"       : round(dc_up, 6),
        "dc_dn"       : round(dc_dn, 6),
        "rsi_cross_up": rsi_cross_up,
        "rsi_cross_dn": rsi_cross_dn,
        "max_score"   : max_score,
        "flow_long"   : flow_long,
        "flow_short"  : flow_short,
        "bb_up"       : round(bb_up_lvl, 6),
        "bb_lo"       : round(bb_lo_lvl, 6),
        "bb_over_long"  : bb_over_long,
        "bb_over_short" : bb_over_short,
        "ema_long_ok"   : ema_long_ok,
        "ema_short_ok"  : ema_short_ok,
        "ema9"          : round(float(ema9.iloc[-1]), 6),
        "ema20_val"     : round(float(ema20.iloc[-1]), 6),
        "ema50_val"     : round(float(ema50.iloc[-1]), 6),
        "long_score"  : long_score,
        "short_score" : short_score,
        "long_trigger"  : long_trigger,
        "short_trigger" : short_trigger,
    }


def calc_entry_trend(df: pd.DataFrame) -> str:
    """EMA9/20/50 hizalamasına göre yön belirle (entry_tf)."""
    ema9  = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
    ema20 = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    if pd.isna(ema9.iloc[-1]) or pd.isna(ema20.iloc[-1]) or pd.isna(ema50.iloc[-1]):
        return "NONE"
    if float(ema9.iloc[-1]) > float(ema20.iloc[-1]) > float(ema50.iloc[-1]):
        return "LONG"
    elif float(ema9.iloc[-1]) < float(ema20.iloc[-1]) < float(ema50.iloc[-1]):
        return "SHORT"
    return "NONE"


def tf_trend(df: pd.DataFrame) -> str:
    """Bir zaman diliminin kısa-vade yönü: EMA fast vs slow. LONG/SHORT/NONE.
    Alt zaman dilimi (5m/15m) teyidi için kullanılır."""
    cfg = CONFIG
    ef = ta.trend.EMAIndicator(df["close"], window=cfg["ltf_ema_fast"]).ema_indicator()
    es = ta.trend.EMAIndicator(df["close"], window=cfg["ltf_ema_slow"]).ema_indicator()
    if pd.isna(ef.iloc[-1]) or pd.isna(es.iloc[-1]):
        return "NONE"
    if   float(ef.iloc[-1]) > float(es.iloc[-1]): return "LONG"
    elif float(ef.iloc[-1]) < float(es.iloc[-1]): return "SHORT"
    return "NONE"


def get_signal(trend: dict, entry: dict, daily: str, btc_chg: float = 0.0,
               entry_trend: str = "NONE", tf5: str = "NONE", tf15: str = "NONE") -> str:
    cfg = CONFIG
    d   = trend["direction"]

    if d == "NONE":          return "HOLD"
    if not trend["adx_ok"]: return "HOLD"
    # Aşırı yüksek ADX = trend YORGUN/aşırı-uzamış → tepeden alım riski, girme.
    if cfg.get("adx_max") and trend["adx"] >= cfg["adx_max"]:
        return "HOLD"

    # Coin momentum filtresi
    coin_chg = entry.get("coin_chg_1h", 0.0)
    if d == "LONG"  and coin_chg <= -0.015: return "HOLD"
    if d == "SHORT" and coin_chg >=  0.015: return "HOLD"

    # Bollinger aşırı-uzama filtresi
    if cfg.get("bb_filter_enabled", True):
        if d == "LONG"  and entry.get("bb_over_long"):  return "HOLD"
        if d == "SHORT" and entry.get("bb_over_short"): return "HOLD"

    # Alt zaman dilimi teyidi: 1h yönü ile 5m VE 15m'in İKİSİ birden ters ise girme.
    # (1h yükselirken 5m+15m düşüyorsa = düşen bıçağı yakalama → engelle; tersi de.)
    if cfg.get("ltf_confirm_enabled", True):
        opp = "SHORT" if d == "LONG" else "LONG"
        if tf5 == opp and tf15 == opp:
            return "HOLD"

    # 1d & 4h uyumu
    if daily != "NONE" and daily != d: return "HOLD"
    # entry_tf (1h) EMA hizalaması ters ise 1 ekstra koşul iste
    min_c = cfg["min_conditions"]
    if entry_trend != "NONE" and entry_trend != d:
        min_c += 1

    # BTC filtresi
    if cfg["btc_filter_enabled"]:
        if d == "LONG"  and btc_chg <= -cfg["btc_drop_threshold"]:
            return "HOLD"
        if d == "SHORT" and btc_chg >=  cfg["btc_pump_threshold"]:
            return "HOLD"

    # Zorunlu tetik
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
        self.leverage       = CONFIG["leverage"]   # bu pozisyonun KENDİ kaldıracı (dinamik)
        self.risk_pct       = 0.0
        self.exchange_sl    = 0.0
        self.entry_snapshot = {}      # giriş anındaki koşullar (CSV günlüğü için)
        self.open_time      = None
        self.cooldown_until = None
        # Kısmi kâr-al durumu
        self.tp1            = 0.0      # kısmi kâr seviyesi (1R)
        self.orig_amount    = 0.0      # açılıştaki tam miktar (kısmi oran için)
        self.partial_done   = False    # yarısı kısmi alındı mı

    def open(self, side: str, price: float, atr: float, amount: float, leverage: int = None):
        cfg  = CONFIG
        cost = (cfg["commission"] + cfg["slippage"]) * 2

        # Kısmi kâr açıksa nihai TP daha uzağa (runner_rr), değilse normal rr_ratio.
        partial = cfg.get("partial_tp_enabled")
        rr      = cfg["partial_runner_rr"] if partial else cfg["rr_ratio"]

        if side == "LONG":
            sl_atr  = price - atr * cfg["atr_sl_mult"]
            sl_hmax = price * (1 - cfg["max_sl_pct"])
            sl_hmin = price * (1 - cfg["min_sl_pct"])
            self.stop_loss   = round(min(max(sl_atr, sl_hmax), sl_hmin), 6)
            sl_dist          = price - self.stop_loss
            self.take_profit = round(price + sl_dist * rr + price * cost, 6)
            self.tp1         = round(price + sl_dist * cfg["partial_tp_r"], 6) if partial else 0.0
            self.trail_sl    = self.stop_loss
            self.peak        = price
            self.valley      = 0.0
        else:
            sl_atr  = price + atr * cfg["atr_sl_mult"]
            sl_hmax = price * (1 + cfg["max_sl_pct"])
            sl_hmin = price * (1 + cfg["min_sl_pct"])
            self.stop_loss   = round(max(min(sl_atr, sl_hmax), sl_hmin), 6)
            sl_dist          = self.stop_loss - price
            self.take_profit = round(price - sl_dist * rr - price * cost, 6)
            self.tp1         = round(price - sl_dist * cfg["partial_tp_r"], 6) if partial else 0.0
            self.trail_sl    = self.stop_loss
            self.valley      = price
            self.peak        = 0.0

        self.orig_amount  = amount
        self.partial_done = False

        self.active      = True
        self.side        = side
        self.entry_price = price
        self.open_time   = time.time()
        self.amount      = amount
        self.leverage    = int(leverage) if leverage else CONFIG["leverage"]
        self.risk_pct    = abs(price - self.stop_loss) / price
        self.exchange_sl = self.stop_loss

        sl_pct = abs(price - self.stop_loss)   / price * 100
        tp_pct = abs(price - self.take_profit) / price * 100
        tp1_line = (f"\n   TP1   : {self.tp1:,.6f}  (+%{abs(price-self.tp1)/price*100:.2f}) "
                    f"→ yarısını kapat, stop başabaşa") if self.tp1 > 0 else ""
        log.info(
            f"📈 [{self.symbol}] {side} AÇILDI\n"
            f"   Giriş : {price:,.6f}  ATR: {atr:,.6f}\n"
            f"   SL    : {self.stop_loss:,.6f}  (-%{sl_pct:.2f}){tp1_line}\n"
            f"   TP    : {self.take_profit:,.6f}  (+%{tp_pct:.2f})\n"
            f"   R:R   : 1:{tp_pct/sl_pct:.1f}  Miktar: {self.amount:.6f}"
        )

    def update_trailing(self, price: float) -> bool:
        cfg        = CONFIG
        risk       = self.risk_pct if self.risk_pct > 0 else cfg["min_sl_pct"]
        min_profit = cfg["trail_start_r"]  * risk
        be_pct     = cfg["breakeven_at_r"] * risk
        base_pct   = cfg["trail_pct"]
        max_pct    = cfg["trail_max_pct"]

        if self.side == "LONG":
            profit = (price - self.entry_price) / self.entry_price
            if profit >= be_pct:
                be = round(self.entry_price * 1.0001, 6)
                if self.stop_loss < be:
                    self.stop_loss = be
                    log.info(f"🔒 [{self.symbol}] Breakeven → {be:,.6f}")
            if profit >= min_profit:
                pct = max_pct if profit >= max_pct else base_pct
                if price > self.peak:
                    self.peak = price
                    new_sl = round(price * (1 - pct), 6)
                    new_sl = max(new_sl, round(self.entry_price * 1.0001, 6))
                    if new_sl > self.trail_sl:
                        self.trail_sl = new_sl
                        if new_sl > self.stop_loss:
                            self.stop_loss = new_sl
                        log.info(f"📶 [{self.symbol}] Trail → {self.trail_sl:,.6f} (peak: {self.peak:,.6f})")
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
                    new_sl = min(new_sl, round(self.entry_price * 0.9999, 6))
                    if new_sl < self.trail_sl:
                        self.trail_sl = new_sl
                        if new_sl < self.stop_loss:
                            self.stop_loss = new_sl
                        log.info(f"📶 [{self.symbol}] Trail → {self.trail_sl:,.6f} (valley: {self.valley:,.6f})")
            trailing_active = self.valley > 0 and self.valley < self.entry_price
            if trailing_active:
                return price >= self.trail_sl
            return False

    def partial_ready(self, price: float) -> bool:
        """+1R'ye (tp1) ulaşıldı ve henüz kısmi alınmadıysa True."""
        if not CONFIG.get("partial_tp_enabled") or self.partial_done or not self.active:
            return False
        if self.tp1 <= 0:
            return False
        return price >= self.tp1 if self.side == "LONG" else price <= self.tp1

    def apply_partial(self, price: float) -> float:
        """Pozisyonun partial_tp_frac kadarını (yarısını) kapatır: kârı kaydeder,
        kalan miktarı düşürür, stop'u başabaşa çeker. Kapatılan miktarı döner."""
        cfg       = CONFIG
        close_amt = round(self.orig_amount * cfg["partial_tp_frac"], 8)

        pnl_pct = (price / self.entry_price - 1) * 100 if self.side == "LONG" \
                  else (self.entry_price / price - 1) * 100
        pnl_lev = pnl_pct * self.leverage
        cost    = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * self.leverage
        pnl_net = pnl_lev - cost
        margin  = close_amt * self.entry_price / self.leverage if self.entry_price > 0 else cfg["trade_usdt"]
        pnl_usdt = margin * pnl_net / 100

        pnl_tracker.record(pnl_net, margin)          # kısmi kârı günlük/oturum PnL'e ekle

        # kalan miktar + başabaş stop
        self.amount       = round(self.amount - close_amt, 8)
        self.partial_done = True
        be = round(self.entry_price * (1.0001 if self.side == "LONG" else 0.9999), 6)
        if self.side == "LONG":
            self.stop_loss = max(self.stop_loss, be)
        else:
            self.stop_loss = min(self.stop_loss, be) if self.stop_loss > 0 else be

        log.info(
            f"💰 [{self.symbol}] KISMİ KÂR: yarısı kapatıldı @ {price:,.6f} "
            f"(net {pnl_net:+.2f}%, {pnl_usdt:+.2f} USDT)\n"
            f"   Kalan {self.amount:.6f} koşuyor → stop başabaşa {self.stop_loss:,.6f}, hedef {self.take_profit:,.6f}"
        )
        # CSV: kısmi kapanış da günlüğe yazılsın
        sn = self.entry_snapshot or {}
        write_trade_log({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": self.symbol.split("/")[0], "side": self.side,
            "entry": self.entry_price, "exit": round(price, 6),
            "pnl_net_pct": round(pnl_net, 2), "pnl_usdt": round(pnl_usdt, 2),
            "reason": "PARTIAL_TP", "dur_min": int((time.time() - self.open_time) / 60) if self.open_time else 0,
            "leverage": self.leverage, "adx": sn.get("adx", ""), "daily": sn.get("daily", ""),
            "tf1h": sn.get("tf1h", ""), "tf5": sn.get("tf5", ""), "tf15": sn.get("tf15", ""),
            "score": sn.get("score", ""), "stoch": sn.get("stoch", ""), "rsi": sn.get("rsi", ""),
            "macd": sn.get("macd", ""), "vol": sn.get("vol", ""), "st": sn.get("st", ""), "ema": sn.get("ema", ""),
        })
        coin = self.symbol.split("/")[0]
        notify(f"💰 <b>{coin} {self.side} KISMİ KÂR</b> (yarısı)\n"
               f"@ {price:g}  PnL: {pnl_net:+.2f}% ({pnl_usdt:+.2f} USDT)\n"
               f"Kalan yarı koşuyor, stop başabaşa çekildi.")
        return close_amt

    def check_exit(self, price: float) -> str | None:
        if not self.active:
            return None

        if CONFIG.get("roi_tp_enabled", False):
            roi_pct = CONFIG.get("roi_tp_pct", 0.035)
            if self.side == "LONG":
                profit = (price - self.entry_price) / self.entry_price * self.leverage
            else:
                profit = (self.entry_price - price) / self.entry_price * self.leverage
            if profit >= roi_pct:
                return "ROI_TP"

        if self.open_time is None:
            self.open_time = time.time()

        # Zaman + Kâr çıkışı: N saattir açık VE kaldıraçlı ROI ≥ %X → kârı kilitle
        if CONFIG.get("time_profit_enabled"):
            hours_open = (time.time() - self.open_time) / 3600
            if hours_open >= CONFIG["time_profit_hours"]:
                if self.side == "LONG":
                    roi = (price - self.entry_price) / self.entry_price * 100 * self.leverage
                else:
                    roi = (self.entry_price - price) / self.entry_price * 100 * self.leverage
                if roi >= CONFIG["time_profit_roi_pct"]:
                    return "ZAMAN_KAR"

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
        pnl_lev = pnl_pct * self.leverage
        cost    = (cfg["commission"] + cfg["slippage"]) * 2 * 100 * self.leverage
        pnl_net = pnl_lev - cost
        dur     = int((time.time() - self.open_time) / 60) if self.open_time else 0
        emoji   = "🟢" if pnl_net >= 0 else "🔴"

        log.info(
            f"{emoji} [{self.symbol}] KAPANDI [{reason}]\n"
            f"   Çıkış : {price:,.6f}  Süre: {dur} dk\n"
            f"   PnL   : brüt {pnl_lev:+.2f}%  net {pnl_net:+.2f}%  (maliyet: -{cost:.2f}%)"
        )
        # PnL'i GERÇEK marja göre kaydet (risk-bazlı boyutta miktar değişkendir).
        # margin = notional/leverage = amount*giriş/leverage. Sabit boyutta bu
        # zaten trade_usdt'ye eşittir → her iki modda da doğru.
        margin  = (self.amount * self.entry_price / self.leverage) if self.entry_price > 0 else cfg["trade_usdt"]
        pnl_usdt = margin * pnl_net / 100
        pnl_tracker.record(pnl_net, margin)
        if reason == "STOP_LOSS" and pnl_net < -1.0:
            # sadece GERÇEK zararlı stop coin yasağı saysın; başabaş (kısmi sonrası) sayılmaz
            pnl_tracker.register_sl(self.symbol)   # günlük coin yasağı sayacı

        # ── İşlem günlüğü (CSV) ──
        sn = self.entry_snapshot or {}
        write_trade_log({
            "time"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol"     : self.symbol.split("/")[0],
            "side"       : self.side,
            "entry"      : self.entry_price,
            "exit"       : round(price, 6),
            "pnl_net_pct": round(pnl_net, 2),
            "pnl_usdt"   : round(pnl_usdt, 2),
            "reason"     : reason,
            "dur_min"    : dur,
            "leverage"   : self.leverage,
            "adx"        : sn.get("adx", ""),
            "daily"      : sn.get("daily", ""),
            "tf1h"       : sn.get("tf1h", ""),
            "tf5"        : sn.get("tf5", ""),
            "tf15"       : sn.get("tf15", ""),
            "score"      : sn.get("score", ""),
            "stoch"      : sn.get("stoch", ""),
            "rsi"        : sn.get("rsi", ""),
            "macd"       : sn.get("macd", ""),
            "vol"        : sn.get("vol", ""),
            "st"         : sn.get("st", ""),
            "ema"        : sn.get("ema", ""),
        })

        # ── Telegram bildirimi ──
        coin = self.symbol.split("/")[0]
        notify(
            f"{emoji} <b>{coin} {self.side} KAPANDI</b> [{reason}]\n"
            f"Giriş {self.entry_price:g} → Çıkış {price:g}\n"
            f"PnL: {pnl_net:+.2f}% ({pnl_usdt:+.2f} USDT)  Süre: {dur}dk\n"
            f"Günlük: {pnl_tracker.daily_pnl:+.2f} USDT"
        )

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
    try:
        ex.cancel_all_orders(symbol)
    except Exception as e:
        log.warning(f"⚠️  [{symbol}] Toplu iptal başarısız, tek tek denenecek: {e}")
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


def calc_amount(ex, symbol: str, price: float, sl_price: float = None, balance: float = None):
    """Pozisyon boyutu + kaldıracı hesaplar. Döner: (amount, leverage) veya None.

    DİNAMİK MOD (dynamic_leverage):
      • Marj = bakiyenin position_pct'i (%20). Max 2 pozisyon → toplam %40.
      • Kaldıraç, risk hedefini (risk_per_trade_pct) tutturacak şekilde:
            lev = risk% / (position_pct × SL_mesafesi%)   → [min_lev, max_lev] aralığına kırpılır
        Yani SL dar → yüksek kaldıraç, SL geniş → düşük; risk hep ~%2 (kırpılmadıkça).
    """
    cfg = CONFIG
    if cfg.get("dynamic_leverage") and sl_price and balance and balance > 0:
        sl_dist = abs(price - sl_price) / price          # kesir
        if sl_dist <= 0:
            return None
        margin    = balance * cfg["position_pct"]        # marj = %20 bakiye
        risk_frac = cfg["risk_per_trade_pct"] / 100.0
        lev       = risk_frac / (cfg["position_pct"] * sl_dist)
        leverage  = int(round(max(cfg["min_leverage"], min(cfg["max_leverage"], lev))))
        raw       = margin * leverage / price
    else:
        leverage  = int(cfg["leverage"])
        raw       = cfg["trade_usdt"] * leverage / price

    if cfg["dry_run"]:
        return round(raw, 6), leverage
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
        log.info(f"⏭️  [{symbol}] Miktar {amount:.6f} < borsa min {min_amt} → ATLANIYOR (bakiye/marj küçük).")
        return None
    if min_cost and notional < float(min_cost):
        log.info(f"⏭️  [{symbol}] Notional {notional:.1f} < borsa min {min_cost} → ATLANIYOR (bakiye/marj küçük).")
        return None
    return amount, leverage


def fetch_live_positions(ex, symbols):
    if CONFIG["dry_run"]:
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
    try:
        trades = ex.fetch_my_trades(symbol, limit=5)
        if trades:
            return float(trades[-1]["price"])
    except Exception:
        pass
    return fallback


def position_is_flat(ex, symbol) -> bool:
    try:
        for p in ex.fetch_positions([symbol]):
            if p.get("symbol") == symbol and abs(float(p.get("contracts") or 0)) > 1e-12:
                return False
        return True
    except Exception:
        return False


def send_close(ex, symbol, side, amount, price) -> bool:
    if CONFIG["dry_run"]:
        log.info(f"[DRY RUN] KAPAT {side} {symbol} @ {price:,.6f}")
        return True

    cancel_open_orders(ex, symbol)
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

    time.sleep(0.5)
    cancel_open_orders(ex, symbol)
    return True

# ─────────────────────────────────────────────────────────────
# RESTART MUTABAKATI
# ─────────────────────────────────────────────────────────────

def compute_sltp(price: float, atr: float, side: str):
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
            try:
                pos.leverage = int(float(p.get("leverage") or CONFIG["leverage"]))
            except Exception:
                pos.leverage = CONFIG["leverage"]

            pos.open_time   = _estimate_open_time(ex, sym, side)
            pos.peak        = entry_price
            pos.valley      = entry_price

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

            if entry_price > 0:
                pos.risk_pct = abs(entry_price - pos.stop_loss) / entry_price
            pos.exchange_sl = pos.stop_loss
            found += 1
        except Exception as e:
            log.warning(f"⚠️  Mutabakat: bir pozisyon işlenemedi: {e}")

    if found:
        log.info(f"🔁 Mutabakat tamam: {found} açık pozisyon borsadan yüklendi")
    else:
        log.info("🔁 Mutabakat: borsada açık pozisyon yok, temiz başlangıç")


def _estimate_open_time(ex, symbol: str, side: str) -> float:
    try:
        trades = ex.fetch_my_trades(symbol, limit=50)
        wanted = "buy" if side == "LONG" else "sell"
        for trade in reversed(trades):
            if trade["side"] == wanted:
                return trade["timestamp"] / 1000
    except Exception:
        pass
    return time.time() - CONFIG["max_pos_hours"] * 1800


# ─────────────────────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────────────────────

def log_scan(sym, trend, entry, signal, pos, daily, entry_trend="NONE"):
    t   = lambda b: "✅" if b else "⬜"
    cfg = CONFIG
    _flow_lbl = "CMF" if cfg.get("use_cmf", True) else "Hacim"
    _maxsc    = entry.get("max_score", 4)

    def _conds(side):   # aktif skor koşullarını dinamik diz (side: "long"/"short")
        md = "macd_up" if side == "long" else "macd_down"
        parts = [f"RSI{t(entry['rsi_'+side])}",
                 f"{_flow_lbl}{t(entry.get('flow_'+side, entry['vol_ok']))}",
                 f"ST{t(entry['st_'+side])}"]
        if cfg.get("stochrsi_in_score", True):
            parts.insert(0, f"StochRSI{t(entry['stoch_'+side])}")
        if cfg.get("macd_in_score", True):
            parts.append(f"MACD{t(entry[md])}")
        if cfg.get("use_donchian", False):
            parts.append(f"Kırılım{t(entry.get('donch_'+side, False))}")
        return " ".join(parts)
    sl_p = entry["atr"] * cfg["atr_sl_mult"] / entry["price"] * 100
    sl_p = min(max(sl_p, cfg["min_sl_pct"] * 100), cfg["max_sl_pct"] * 100)
    tp_p = sl_p * cfg["rr_ratio"]

    trail_info = ""
    if pos.active:
        if pos.side == "LONG":
            pnl = (entry["price"] / pos.entry_price - 1) * 100 * pos.leverage
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Peak: {pos.peak:,.6f})\n  Anlık PnL : {pnl:+.2f}%"
        else:
            pnl = (pos.entry_price / entry["price"] - 1) * 100 * pos.leverage
            trail_info = f"\n  Trail SL  : {pos.trail_sl:,.6f}  (Valley: {pos.valley:,.6f})\n  Anlık PnL : {pnl:+.2f}%"

    daily_ok  = daily == "NONE" or daily == trend["direction"]
    ema_ok    = (trend["direction"] == "LONG"  and trend["ema20"] > trend["ema50"]) or \
                (trend["direction"] == "SHORT" and trend["ema20"] < trend["ema50"])

    ema_line = f"EMA9={entry['ema9']:,.4f}  EMA20={entry['ema20_val']:,.4f}  EMA50={entry['ema50_val']:,.4f}"

    # ── Sadece KULLANILAN indikatörlerin okumaları ───────────
    _cmf = entry.get('cmf', 0)
    _rl = [f"  RSI  : {entry['rsi']:.1f}",
           f"  ST   : {entry['st_val']:,.6f}  {'📈' if entry['st_long'] else '📉'}",
           f"  CMF  : {_cmf:+.3f}  {'🟢alım' if _cmf>0 else '🔴satım' if _cmf<0 else '➖'}"]
    if cfg.get("stochrsi_in_score", True):
        _rl.append(f"  StochRSI: K={entry['sk']:.1f}  D={entry['sd']:.1f}")
    if cfg.get("macd_in_score", True) or cfg.get("macd_in_trigger", True):
        _rl.append(f"  MACD : {entry['macd']:.6f}  Sig: {entry['msig']:.6f}")
    if not cfg.get("use_cmf", True):
        _rl.append(f"  Hacim: {entry['volume']:.0f}  (Ort:{entry['vol_ma']:.0f})  {t(entry['vol_ok'])}")
    _ind_lines = "\n".join(_rl)

    # Tetik durumu (neden girdi/girmedi netleşsin)
    if cfg.get("use_donchian", False):
        _st_on = cfg.get("stochrsi_in_trigger", False)
        _st_ev = _st_on and (entry.get('stoch_long') or entry.get('stoch_short'))
        _trg_l = entry.get('donch_long') or entry.get('rsi_cross_up') or (_st_on and entry.get('stoch_long'))
        _trg_s = entry.get('donch_short') or entry.get('rsi_cross_dn') or (_st_on and entry.get('stoch_short'))
        _trg_txt = (f"  Tetik: {'✅' if (_trg_l or _trg_s) else '⬜ YOK'}  "
                    f"(Kırılım:{t(entry.get('donch_long') or entry.get('donch_short'))} "
                    f"RSI50geçiş:{t(entry.get('rsi_cross_up') or entry.get('rsi_cross_dn'))}"
                    + (f" StochRSI:{t(_st_ev)}" if _st_on else "") + ")")
    else:
        _trg_txt = f"  Tetik: L{t(entry['long_trigger'])} S{t(entry['short_trigger'])}"

    log.info(
        f"\n{'─'*54}\n"
        f"  [{sym}]\n"
        f"  1d: {'✅' if daily_ok else '⬜'} {daily}  "
        f"4h: {'📈' if trend['direction']=='LONG' else '📉' if trend['direction']=='SHORT' else '➡'} {trend['direction']}  "
        f"entry: {'📈' if entry_trend=='LONG' else '📉' if entry_trend=='SHORT' else '➡'} {entry_trend}\n"
        f"  EMA  : 20={trend['ema20']:,.4f}  50={trend['ema50']:,.4f}  200={trend['ema200']:,.4f}  {'✅' if ema_ok else '⬜'}\n"
        f"  {ema_line}\n"
        f"  ADX  : {trend['adx']:.1f}  {'✅ güçlü' if trend['adx_ok'] else '⬜ yatay'}\n"
        f"  Fiyat: {entry['price']:>16,.6f}   ATR: {entry['atr']:,.6f}\n"
        f"  SL±{sl_p:.2f}%  TP±{tp_p:.2f}%  R:R 1:{tp_p/sl_p:.1f}\n"
        f"{_ind_lines}\n"
        f"  BB   : üst={entry['bb_up']:,.6f}  alt={entry['bb_lo']:,.6f}  "
        f"{'⚠️ AŞIRI-UZAMA (giriş engel)' if (entry['bb_over_long'] or entry['bb_over_short']) else '✅ bant içi'}\n"
        + (f"  Donchian: üst={entry.get('dc_up',0):,.6f}  alt={entry.get('dc_dn',0):,.6f}  "
           f"{'🟢kırılım↑' if entry.get('donch_long') else '🔴kırılım↓' if entry.get('donch_short') else '➖ bant içi'}\n"
           if cfg.get("use_donchian", False) else "") +
        f"  EMA Kapı: {'✅ hizalı' if (entry['ema_long_ok'] or entry['ema_short_ok']) else '⬜ hizasız'}\n"
        f"  LONG ({entry['long_score']}/{_maxsc}, min={cfg['min_conditions']}): {_conds('long')}\n"
        f"  SHORT({entry['short_score']}/{_maxsc}, min={cfg['min_conditions']}): {_conds('short')}\n"
        f"{_trg_txt}\n"
        f"  Sinyal: {signal}   Pozisyon: {pos.side if pos.active else 'YOK'}"
        f"{trail_info}\n"
        f"{'─'*54}"
    )

# ─────────────────────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────────────────────

def count_open(positions: dict) -> int:
    return sum(1 for p in positions.values() if p.active)


def count_open_side(positions: dict, side: str) -> int:
    """Belirli YÖNDE (LONG/SHORT) açık pozisyon sayısı — korelasyon koruması için."""
    return sum(1 for p in positions.values() if p.active and p.side == side)


def total_margin(positions: dict) -> float:
    """Tüm açık pozisyonların kullandığı toplam marj (USDT) — maruziyet kontrolü için."""
    return sum(p.amount * p.entry_price / p.leverage
               for p in positions.values()
               if p.active and p.entry_price > 0 and p.leverage > 0)


def log_open_positions(ex, positions: dict) -> float:
    """Açık pozisyonları ve gerçekleşmemiş (unrealized) PnL'lerini gösterir.
    Toplam açık USDT PnL'i döner."""
    cfg = CONFIG
    open_pos = [p for p in positions.values() if p.active]
    if not open_pos:
        return 0.0
    lines = [f"📂 AÇIK POZİSYONLAR ({len(open_pos)}/{cfg['max_positions']}):"]
    total_usdt = 0.0
    for p in open_pos:
        price = fetch_current_price(ex, p.symbol) or p.entry_price
        if p.side == "LONG":
            pnl_pct = (price / p.entry_price - 1) * 100
            usdt    = p.amount * (price - p.entry_price)
        else:
            pnl_pct = (p.entry_price / price - 1) * 100
            usdt    = p.amount * (p.entry_price - price)
        pnl_lev = pnl_pct * p.leverage           # marj üzerindeki % (kaldıraçlı)
        total_usdt += usdt
        dur   = int((time.time() - p.open_time) / 60) if p.open_time else 0
        emoji = "🟢" if pnl_lev >= 0 else "🔴"
        coin  = p.symbol.split("/")[0]
        arrow = "📈" if p.side == "LONG" else "📉"
        lines.append(
            f"   {emoji} {arrow} {coin:<6} {p.side:<5}  "
            f"giriş={p.entry_price:,.6f} → {price:,.6f}  "
            f"PnL: {pnl_lev:+.2f}% ({usdt:+.2f} USDT)  "
            f"SL={p.stop_loss:,.6f} TP={p.take_profit:,.6f}  {dur}dk"
        )
    lines.append(f"   ───── Toplam açık (gerçekleşmemiş): {total_usdt:+.2f} USDT ─────")
    log.info("\n".join(lines))
    return total_usdt


def run_symbol(ex, symbol, pos, positions, btc_chg: float = 0.0, live_pos=None, allow_entry: bool = True, balance: float = 0.0):
    cfg = CONFIG
    price = fetch_current_price(ex, symbol)
    if price is None:
        log.warning(f"⚠️ [{symbol}] Anlık fiyat alınamadı, bu döngü atlanıyor")
        return

    if pos.active:
        if live_pos is not None and abs(live_pos.get(symbol, 0.0)) < 1e-12:
            exit_px = fetch_exit_price(ex, symbol, price)
            try:
                cancel_open_orders(ex, symbol)
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

        # Kısmi kâr: +1R'ye geldiyse yarısını kapat, kalan yarı koşmaya devam etsin.
        if pos.partial_ready(price):
            close_amt = round(pos.orig_amount * cfg["partial_tp_frac"], 8)
            ok = send_close(ex, symbol, pos.side, close_amt, price)
            if ok:
                pos.apply_partial(price)
                # kalan yarı için başabaş stop'u borsaya yansıt
                if cfg.get("sync_trailing_to_exchange") and not cfg["dry_run"]:
                    try:
                        update_exchange_stop(ex, pos)
                    except Exception:
                        pass
            # pozisyon hâlâ açık → return YOK, aynı döngüde çıkış da kontrol edilebilir

        reason = pos.check_exit(price)
        if reason:
            ok = send_close(ex, symbol, pos.side, pos.amount, price)
            if ok:
                pos.close(price, reason)
            return

        if cfg.get("sync_trailing_to_exchange") and pos.entry_price > 0:
            moved = abs(pos.stop_loss - pos.exchange_sl) / pos.entry_price
            if moved >= cfg["sl_sync_threshold_pct"]:
                update_exchange_stop(ex, pos)
        return

    if pos.active:
        return
    if not allow_entry:
        return
    if pos.in_cooldown():
        mins = int((pos.cooldown_until - time.time()) / 60) + 1
        log.info(f"⏸️  [{symbol}] Cooldown: {mins} dk")
        return
    if pnl_tracker.is_coin_banned(symbol):
        n = pnl_tracker.daily_sl_count.get(symbol, 0)
        log.info(f"🚫 [{symbol}] Bugün {n} kez SL yedi → gün sonuna kadar YASAK (tekrar-deneme freni)")
        return
    if count_open(positions) >= cfg["max_positions"]:
        return

    try:
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

        entry_trend = calc_entry_trend(df1h)

        # Alt zaman dilimi teyidi (5m + 15m) — ters yönde giriş engellenir
        tf5 = tf15 = "NONE"
        if cfg.get("ltf_confirm_enabled", True):
            try:
                df5  = fetch_ohlcv_cached(ex, symbol, "5m",  120, 60).iloc[:-1].copy()
                df15 = fetch_ohlcv_cached(ex, symbol, "15m", 120, 120).iloc[:-1].copy()
                tf5  = tf_trend(df5)
                tf15 = tf_trend(df15)
            except Exception:
                pass

        signal   = get_signal(trend, entry, daily, btc_chg, entry_trend, tf5, tf15)

        log_scan(symbol, trend, entry, signal, pos, daily, entry_trend)

        if signal in ("LONG", "SHORT"):
            # Boyut+kaldıraç için önce SL'i hesapla (pos.open ile AYNI formül)
            sl_pre, _ = compute_sltp(price, entry["atr"], signal)
            res  = calc_amount(ex, symbol, price, sl_pre, balance)
            _mpd = cfg.get("max_per_direction", 0)
            # Yeni pozisyonun marjı ve toplam maruziyet kontrolü
            new_margin = balance * cfg["position_pct"] if cfg.get("dynamic_leverage") else cfg["trade_usdt"]
            exposure_full = (cfg.get("dynamic_leverage") and balance > 0
                             and total_margin(positions) + new_margin > balance * cfg["total_exposure_pct"] + 1e-9)
            if res is None:
                pass
            elif _mpd and count_open_side(positions, signal) >= _mpd:
                log.info(f"⚖️  [{symbol}] Aynı yönde ({signal}) zaten pozisyon var → korelasyon koruması, atla")
            elif exposure_full:
                log.info(f"⛔ [{symbol}] Toplam maruziyet %{cfg['total_exposure_pct']*100:.0f} dolu → atla")
            elif not spread_ok(ex, symbol, cfg["max_spread_pct"]):
                pass
            else:
                amount, lev = res
                if not ensure_leverage(ex, symbol, lev):
                    pass   # kaldıraç kurulamadı → açma
                else:
                    pos.open(signal, price, entry["atr"], amount, lev)
                    # Giriş anındaki koşulları sakla (CSV günlüğü için)
                    L = signal == "LONG"
                    pos.entry_snapshot = {
                        "adx": trend["adx"], "daily": daily, "tf1h": entry_trend, "tf5": tf5, "tf15": tf15,
                        "score": entry["long_score"] if L else entry["short_score"],
                        "stoch": entry["stoch_long"] if L else entry["stoch_short"],
                        "rsi":   entry["rsi_long"]   if L else entry["rsi_short"],
                        "macd":  entry["macd_up"]    if L else entry["macd_down"],
                        "vol":   entry["vol_ok"],
                        "st":    entry["st_long"]    if L else entry["st_short"],
                        "ema":   entry["ema_long_ok"] if L else entry["ema_short_ok"],
                    }
                    ok = send_open(ex, symbol, signal, pos.amount, price, pos.stop_loss, pos.take_profit)
                    if not ok:
                        log.warning(f"⚠️  [{symbol}] Emir başarısız, pozisyon hafızadan siliniyor")
                        pos.active = False
                        pos.side = None
                    else:
                        coin = symbol.split("/")[0]
                        sl_pct = abs(price - pos.stop_loss) / price * 100
                        tp_pct = abs(price - pos.take_profit) / price * 100
                        margin = pos.amount * price / pos.leverage
                        notify(
                            f"{'🟢' if L else '🔴'} <b>{coin} {signal} AÇILDI</b>\n"
                            f"Giriş: {price:g}  Kaldıraç: {pos.leverage}x  Marj: {margin:.1f} USDT\n"
                            f"SL: {pos.stop_loss:g} (-%{sl_pct:.2f})  TP: {pos.take_profit:g} (+%{tp_pct:.2f})"
                        )

    except ccxt.NetworkError as e:
        log.warning(f"🌐 [{symbol}] Ağ: {e}")
    except ccxt.ExchangeError as e:
        log.error(f"🏦 [{symbol}] Borsa: {e}")
    except Exception as e:
        log.exception(f"💥 [{symbol}] Hata: {e}")
        notify(f"💥 <b>{symbol.split('/')[0]} HATA</b>: {str(e)[:200]}")


def main():
    global START_BALANCE
    cfg  = CONFIG
    ex   = connect_exchange()
    START_BALANCE   = fetch_balance(ex)
    current_balance = START_BALANCE
    last_bal_refresh = time.time()
    last_refresh  = time.time()
    symbols = build_scan_list(ex)

    log.info("=" * 54)
    log.info("  🤖 Kripto Futures Bot v10.0 — EMA9 EKLENDİ")
    log.info(f"  Bakiye     : {START_BALANCE:.2f} USDT")
    if cfg["symbols"]:
        _scan_mode = "sabit liste"
    else:
        _scan_mode = f"{len(cfg.get('core_symbols', []))} ana + saatlik top {cfg['top_volatile_count']} volatil"
    log.info(f"  Coinler    : {len(symbols)} coin — {_scan_mode}  (max {cfg['max_positions']} pozisyon)")
    if cfg.get("dynamic_leverage"):
        log.info(f"  Kaldıraç   : DİNAMİK {cfg['min_leverage']}-{cfg['max_leverage']}x (risk hedefine göre)")
        log.info(f"  Boyut      : marj=%{cfg['position_pct']*100:.0f} bakiye/pozisyon  toplam≤%{cfg['total_exposure_pct']*100:.0f}  risk≈%{cfg['risk_per_trade_pct']}")
    elif cfg.get("risk_based_sizing"):
        log.info(f"  Kaldıraç   : {cfg['leverage']}x")
        log.info(f"  Boyut      : risk-bazlı — her işlemde bakiyenin %{cfg['risk_per_trade_pct']}'i riskte")
    else:
        log.info(f"  Kaldıraç   : {cfg['leverage']}x")
        log.info(f"  Boyut      : sabit {cfg['trade_usdt']} USDT")
    log.info(f"  Zarar Freni: üst üste {cfg['consec_loss_limit']} zarar → {cfg['consec_loss_pause_hours']}s mola")
    log.info(f"  SL/TP      : SL ×{cfg['atr_sl_mult']} ATR (min %{cfg['min_sl_pct']*100:.1f})  R:R 1:{cfg['rr_ratio']:.1f}")
    _mx = 3 + (1 if cfg.get('stochrsi_in_score', True) else 0) + (1 if cfg.get('macd_in_score', True) else 0) + (1 if cfg.get('use_donchian', False) else 0)
    _set = ["RSI", ("CMF" if cfg.get("use_cmf", True) else "Hacim"), "SuperTrend"]
    if cfg.get("stochrsi_in_score", True): _set.insert(0, "StochRSI")
    if cfg.get("macd_in_score", True):     _set.append("MACD")
    if cfg.get("use_donchian", False):     _set.append("Donchian")
    log.info(f"  Min Koşul  : {cfg['min_conditions']}/{_mx} koşul + zorunlu tetik + EMA9/20/50 kapısı")
    log.info(f"  Skor Seti  : {' + '.join(_set)}  (bağımsız aileler)")
    if cfg.get("use_donchian", False):
        _trig = "Donchian kırılımı VEYA RSI-50 geçişi" + (" VEYA StochRSI dönüşü" if cfg.get("stochrsi_in_trigger", False) else "")
    else:
        _trig = "MACD/StochRSI" if cfg.get("macd_in_trigger", True) else "StochRSI"
    log.info(f"  Tetik      : {_trig}")
    log.info(f"  BB Filtre  : {'açık (aşırı-uzamada girme)' if cfg.get('bb_filter_enabled', True) else 'kapalı'}")
    log.info(f"  ADX Eşiği  : {cfg['adx_threshold']} – {cfg.get('adx_max', '∞')} (üstü yorgun trend → girme)")
    log.info(f"  Coin Yasağı: günde {cfg.get('daily_coin_ban_sl', 0)} SL → o coin gün sonuna kadar yasak")
    log.info(f"  Cooldown   : SL={cfg['cooldown_sl_sec']//60}dk  TP={cfg['cooldown_tp_sec']//60}dk")
    log.info(f"  Zarar Lim  : {('%'+str(cfg['daily_loss_pct'])) if cfg.get('daily_loss_enabled', False) else 'KAPALI'}")
    log.info(f"  Kâr Hedefi : +%{cfg['daily_profit_target_pct']:.0f} → {cfg['profit_pause_hours']}s mola")
    if cfg.get("roi_tp_enabled"):
        log.info(f"  ROI TP     : +%{cfg['roi_tp_pct']*100:.1f} kaldıraçlı kârda anında kapat (aktif)")
    log.info(f"  Mod        : {'🧪 DRY RUN' if cfg['dry_run'] else '💰 CANLI'}")
    log.info("=" * 54)
    notify(
        f"🤖 <b>Bot başladı</b>\n"
        f"Bakiye: {START_BALANCE:.2f} USDT  Kaldıraç: {cfg['leverage']}x\n"
        f"{len(symbols)} coin  Max {cfg['max_positions']} pozisyon\n"
        f"Mod: {'🧪 DRY RUN' if cfg['dry_run'] else '💰 CANLI'}"
    )

    positions = {}
    for sym in symbols:
        positions[sym] = Position(sym)
        setup_symbol(ex, sym, cfg["leverage"])
        time.sleep(0.2)

    for sym in cfg.get("core_symbols", []):
        positions.setdefault(sym, Position(sym))

    reconcile_positions(ex, positions)

    held = [s for s, p in positions.items() if p.active and s not in symbols]
    if held:
        log.info(f"📌 Tarama dışı açık pozisyonlar yönetime alındı: {', '.join(held)}")
        symbols = symbols + held

    pause_until = 0.0
    pause_day   = None
    while True:
        if not cfg["dry_run"] and time.time() - last_bal_refresh > cfg["balance_refresh_sec"]:
            b = fetch_balance_quiet(ex)
            if b is not None:
                current_balance = b
            last_bal_refresh = time.time()

        if cfg.get("daily_loss_enabled", False) and pnl_tracker.daily_limit_hit(current_balance):
            log.warning("💤 Günlük zarar limiti → 1 saat bekleniyor...")
            notify(f"🛑 <b>Günlük zarar limiti (-%{cfg['daily_loss_pct']:.0f})</b> → 1 saat mola. Günlük: {pnl_tracker.daily_pnl:+.2f} USDT")
            time.sleep(3600)
            continue

        if pause_day != date.today() and pnl_tracker.daily_profit_hit(current_balance, cfg["daily_profit_target_pct"]):
            pause_until = time.time() + cfg["profit_pause_hours"] * 3600
            pause_day   = date.today()
            log.info(f"🎯 Günlük +%{cfg['daily_profit_target_pct']:.0f} hedefe ulaşıldı → "
                     f"{cfg['profit_pause_hours']} saat YENİ işlem YOK (açık pozisyonlar yönetiliyor)")
            notify(f"🎯 <b>Günlük +%{cfg['daily_profit_target_pct']:.0f} hedef!</b> {cfg['profit_pause_hours']}s yeni işlem yok. Günlük: {pnl_tracker.daily_pnl:+.2f} USDT")

        # #2 Üst üste zarar freni: N zarar arka arkaya → M saat mola (whipsaw kesici)
        if pnl_tracker.consecutive_losses >= cfg["consec_loss_limit"]:
            pause_until = max(pause_until, time.time() + cfg["consec_loss_pause_hours"] * 3600)
            log.warning(f"🧊 {pnl_tracker.consecutive_losses} üst üste zarar → "
                        f"{cfg['consec_loss_pause_hours']} saat YENİ işlem YOK (whipsaw freni)")
            notify(f"🧊 <b>{pnl_tracker.consecutive_losses} üst üste zarar</b> → {cfg['consec_loss_pause_hours']}s yeni işlem yok (whipsaw freni)")
            pnl_tracker.consecutive_losses = 0   # sıfırla ki tekrar tetiklemesin

        allow_entry = time.time() >= pause_until

        if not cfg["symbols"] and time.time() - last_refresh > cfg["symbol_refresh_sec"]:
            log.info("🔄 Volatil coinler yenileniyor (ana coinler sabit kalır)...")
            new_syms = build_scan_list(ex)
            for s in new_syms:
                if s not in positions:
                    positions[s] = Position(s)
                    setup_symbol(ex, s, cfg["leverage"])
            held = [s for s, p in positions.items() if p.active and s not in new_syms]
            if held:
                log.info(f"📌 Açık pozisyonlu coinler listede tutuluyor: {', '.join(held)}")
            symbols      = list(dict.fromkeys(new_syms + held))
            last_refresh = time.time()

        btc_chg = get_btc_change(ex)
        if CONFIG["btc_filter_enabled"]:
            log.info(f"📊 BTC 1h değişim: {btc_chg*100:+.2f}%  {'🔴 LONG engel' if btc_chg <= -CONFIG['btc_drop_threshold'] else '🟢 SHORT engel' if btc_chg >= CONFIG['btc_pump_threshold'] else '✅ normal'}")

        live_pos = fetch_live_positions(ex, symbols)

        if not allow_entry:
            mins = int((pause_until - time.time()) / 60) + 1
            log.info(f"🎯 Kâr hedefi molası: {mins} dk daha yeni işlem yok (açık pozisyonlar yönetiliyor)")

        # PARALEL ÖN-TARAMA: giriş mümkünse, aday coinlerin mumlarını 5 thread ile
        # aynı anda çekip cache'i ısıt. Sonraki sıralı döngü cache'ten okur → çok hızlı.
        if cfg.get("parallel_scan") and allow_entry and count_open(positions) < cfg["max_positions"]:
            cands = [s for s in symbols if not positions[s].active and not positions[s].in_cooldown()]
            t0 = time.time()
            prefetch_ohlcv(ex, cands)
            log.info(f"⚡ Paralel tarama: {len(cands)} coin {cfg['scan_workers']} thread ile {time.time()-t0:.1f}s'de tarandı")

        _sym_sleep = 0.1 if cfg.get("parallel_scan") else 0.5   # cache sıcaksa bekleme kısa
        for sym in symbols:
            run_symbol(ex, sym, positions[sym], positions, btc_chg, live_pos, allow_entry, current_balance)
            time.sleep(_sym_sleep)

        # Açık pozisyonları ve gerçekleşmemiş PnL'leri göster
        open_usdt = log_open_positions(ex, positions)

        open_c = count_open(positions)
        wr = pnl_tracker.wins / pnl_tracker.total * 100 if pnl_tracker.total else 0
        log.info(
            f"⏳ {cfg['loop_sec']}s bekleniyor...  "
            f"[Açık: {open_c}/{cfg['max_positions']} ({open_usdt:+.2f} USDT)  "
            f"Oturum: {pnl_tracker.session_pnl:+.2f} USDT  "
            f"Günlük: {pnl_tracker.daily_pnl:+.2f} USDT  "
            f"WR: %{wr:.0f} ({pnl_tracker.wins}W/{pnl_tracker.losses}L)]\n"
        )
        time.sleep(cfg["loop_sec"])


if __name__ == "__main__":
    main()