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

  KATMAN 4 — GİRİŞ (1h, 2/6 koşul yeterli)
    StochRSI aşırı bölge + dönüş
    RSI aşırı bölge
    MACD crossover
    Hacim artışı
    OBV yönü
    Süper Trend yönü

── ÇIKIŞ ────────────────────────────────────────────────────────
  SL      : ATR × 0.8  (min %0.8, max %1.8)
  TP      : ATR × 1.6  → R:R 1:2  (alternatif)
  ROI TP  : +%3.5 kaldıraçlı kâr → direkt kapat (şu an aktif)
  Trailing: %1.5  (min %1.0 kârda devreye girer)
  Breakeven: %1.2 kârda SL → giriş fiyatına
  Zaman   : 5 saat içinde kapanmazsa çık

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
    "symbols"             : [
        "BTC/USDT:USDT",  "ETH/USDT:USDT",  "SOL/USDT:USDT",
        "BNB/USDT:USDT",  "XRP/USDT:USDT",  "DOGE/USDT:USDT",
        "ADA/USDT:USDT",  "AVAX/USDT:USDT", "LINK/USDT:USDT",
        "LTC/USDT:USDT",  "BCH/USDT:USDT",  "NEAR/USDT:USDT",
        "AAVE/USDT:USDT", "FIL/USDT:USDT",
        "DOT/USDT:USDT",  "UNI/USDT:USDT",  "ATOM/USDT:USDT",
        "ARB/USDT:USDT",  "OP/USDT:USDT",   "SUI/USDT:USDT",
        "INJ/USDT:USDT",  "APT/USDT:USDT",  "TIA/USDT:USDT",
    ],
    "top_volatile_count"  : 50,          # 50 coin tara
    "symbol_refresh_sec"  : 3600,        # saatte bir yenile

    # ── Kaldıraç ────────────────────────────────────────────
    "leverage"            : 5,

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
    "adx_threshold"       : 20,

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
    "atr_sl_mult"         : 0.8,
    "atr_tp_mult"         : 1.6,         # R:R 1:2 (ROI TP aktifse ikincil)
    "min_sl_pct"          : 0.008,
    "max_sl_pct"          : 0.018,

    # ── Trailing & Breakeven ─────────────────────────────────
    "trail_pct"           : 0.012,
    "trail_min_profit"    : 0.010,       # %1.0 kârda trailing devreye girer
    "trail_max_pct"       : 0.025,
    "breakeven_pct"       : 0.015,       # %1.5 kârda breakeven

    # ── Giriş eşiği ─────────────────────────────────────────
    "min_conditions"      : 3,    # 6 koşuldan kaçı sağlanmalı

    # ── Risk ─────────────────────────────────────────────────
    "trade_usdt"          : 10,
    "max_positions"       : 2,
    "daily_loss_pct"      : 8.0,
    "cooldown_sl_sec"     : 3600,
    "cooldown_tp_sec"     : 600,
    "max_pos_hours"       : 4,            # 4 saat içinde kapanmazsa çık

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

    def record(self, pnl_pct: float, usdt: float):
        pnl_usdt = usdt * pnl_pct / 100
        self.session_pnl += pnl_usdt
        self.total       += 1
        if date.today() != self.daily_date:
            self.daily_pnl  = 0.0
            self.daily_date = date.today()
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
        if balance <= 0:
            return False
        if self.daily_pnl < 0 and abs(self.daily_pnl) / balance * 100 >= CONFIG["daily_loss_pct"]:
            log.warning(f"🛑 Günlük limit → 1 saat duruyor")
            return True
        return False

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

# ─────────────────────────────────────────────────────────────
# SEMBOL SEÇİCİ
# ─────────────────────────────────────────────────────────────

STABLE   = {"USDT","BUSD","USDC","DAI","TUSD","FDUSD","USDP","UST"}
FALLBACK = ["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","BNB/USDT:USDT","XRP/USDT:USDT"]


def get_symbols(ex: ccxt.Exchange, top_n: int) -> list[str]:
    log.info("🔍 Coin taraması başlıyor...")
    try:
        markets = ex.load_markets()
        tickers = ex.fetch_tickers()
    except Exception as e:
        log.error(f"Tarama hatası: {e}")
        return FALLBACK

    valid = {
        m["symbol"] for m in markets.values()
        if m.get("type") == "swap" and m.get("linear")
        and m.get("active") and m.get("quote") == "USDT"
        and m.get("base") not in STABLE
    }

    rows = []
    for sym, t in tickers.items():
        if sym not in valid:
            continue
        vol = t.get("quoteVolume") or 0
        pct = abs(t.get("percentage") or 0)
        if vol < 10_000_000:  # min 10M USDT hacim
            continue
        rows.append({"symbol": sym, "pct": pct, "vol_m": vol / 1e6, "score": pct * vol})

    if not rows:
        return FALLBACK

    df = pd.DataFrame(rows).sort_values("score", ascending=False).head(top_n)

    log.info(f"🏆 En volatil {top_n} coin (hepsi taranacak, max {CONFIG['max_positions']} pozisyon açılacak):")
    for _, r in df.iterrows():
        log.info(f"   {r['symbol']:<28}  %{r['pct']:>5.1f}  {r['vol_m']:>8.1f}M")
    return df["symbol"].tolist()

# ─────────────────────────────────────────────────────────────
# VERİ
# ─────────────────────────────────────────────────────────────

def fetch_ohlcv(ex: ccxt.Exchange, symbol: str, tf: str, limit: int = 300) -> pd.DataFrame:
    raw = ex.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    df  = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df.set_index("ts", inplace=True)
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

    # OBV
    df["obv"]    = ta.volume.OnBalanceVolumeIndicator(
        df["close"], df["volume"]
    ).on_balance_volume()
    df["obv_ma"] = df["obv"].rolling(20).mean()

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    price = float(last["close"])

    # Coin kendi 1h momentum kontrolü
    coin_chg_1h = (price - float(prev["close"])) / float(prev["close"])

    # NaN Koruması
    for col in ["sk","sd","macd","msig","st","atr","vol_ma","obv","obv_ma","rsi"]:
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
    # Trend takip: LONG için RSI yükseliyor ve 45 üstünde, SHORT için düşüyor ve 55 altında
    rsi_long  = rsi_val > cfg["rsi_oversold"]   and sk_rising
    rsi_short = rsi_val < cfg["rsi_overbought"] and sk_falling

    st_long  = int(last["std"]) == 1
    st_short = int(last["std"]) == -1
    vol_ok   = float(last["volume"]) > float(last["vol_ma"]) * cfg["vol_mult"]
    obv_long  = float(last["obv"]) > float(last["obv_ma"])
    obv_short = float(last["obv"]) < float(last["obv_ma"])

    # Skor: StochRSI + RSI + MACD + Hacim + OBV + ST (hepsi skorda, zorunlu yok)
    long_score  = sum([stoch_long,  rsi_long,  macd_up,   vol_ok, obv_long,  st_long])
    short_score = sum([stoch_short, rsi_short, macd_down, vol_ok, obv_short, st_short])

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
        "obv_long"    : obv_long,
        "obv_short"   : obv_short,
        "volume"      : float(last["volume"]),
        "vol_ma"      : float(last["vol_ma"]),
        "long_score"  : long_score,
        "short_score" : short_score,
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
            self.take_profit = round(price * (1 + atr * cfg["atr_tp_mult"] / price + cost), 6)
            self.trail_sl    = self.stop_loss        # başlangıçta SL ile aynı
            self.peak        = price
            self.valley      = 0.0
        else:
            sl_atr  = price + atr * cfg["atr_sl_mult"]
            sl_hmax = price * (1 + cfg["max_sl_pct"])
            sl_hmin = price * (1 + cfg["min_sl_pct"])
            self.stop_loss   = round(max(min(sl_atr, sl_hmax), sl_hmin), 6)
            self.take_profit = round(price * (1 - atr * cfg["atr_tp_mult"] / price - cost), 6)
            self.trail_sl    = self.stop_loss        # başlangıçta SL ile aynı
            self.valley      = price
            self.peak        = 0.0

        self.active      = True
        self.side        = side
        self.entry_price = price
        self.open_time   = time.time()
        self.amount      = amount   # caller'dan gelen, borsa precision'ına uygun miktar

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
        min_profit = cfg["trail_min_profit"]
        base_pct   = cfg["trail_pct"]
        max_pct    = cfg["trail_max_pct"]
        be_pct     = cfg["breakeven_pct"]

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
        return {}
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
        tp = round(price * (1 + atr * cfg["atr_tp_mult"] / price + cost), 6)
    else:
        sl_atr  = price + atr * cfg["atr_sl_mult"]
        sl_hmax = price * (1 + cfg["max_sl_pct"])
        sl_hmin = price * (1 + cfg["min_sl_pct"])
        sl = round(max(min(sl_atr, sl_hmax), sl_hmin), 6)
        tp = round(price * (1 - atr * cfg["atr_tp_mult"] / price - cost), 6)
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
    sl_p = entry["atr"] * cfg["atr_sl_mult"] / entry["price"] * 100
    tp_p = entry["atr"] * cfg["atr_tp_mult"] / entry["price"] * 100

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
        f"  LONG ({entry['long_score']}/6, min={cfg['min_conditions']}): "
        f"StochRSI{t(entry['stoch_long'])} RSI{t(entry['rsi_long'])} MACD{t(entry['macd_up'])} Hacim{t(entry['vol_ok'])} OBV{t(entry['obv_long'])} ST{t(entry['st_long'])}\n"
        f"  SHORT({entry['short_score']}/6, min={cfg['min_conditions']}): "
        f"StochRSI{t(entry['stoch_short'])} RSI{t(entry['rsi_short'])} MACD{t(entry['macd_down'])} Hacim{t(entry['vol_ok'])} OBV{t(entry['obv_short'])} ST{t(entry['st_short'])}\n"
        f"  Sinyal: {signal}   Pozisyon: {pos.side if pos.active else 'YOK'}"
        f"{trail_info}\n"
        f"{'─'*54}"
    )

# ─────────────────────────────────────────────────────────────
# ANA DÖNGÜ
# ─────────────────────────────────────────────────────────────

def count_open(positions: dict) -> int:
    return sum(1 for p in positions.values() if p.active)


def run_symbol(ex, symbol, pos, positions, btc_chg: float = 0.0, live_pos=None):
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

    # ── 3. Sinyal hesaplamaları (sadece yeni giriş için gerekli) ──
    try:
        df1d = fetch_ohlcv(ex, symbol, cfg["daily_tf"],  limit=210)
        df4h = fetch_ohlcv(ex, symbol, cfg["trend_tf"],  limit=250)
        df1h = fetch_ohlcv(ex, symbol, cfg["entry_tf"],  limit=300)

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

        # Yeni pozisyon açma kararı
        if not pos.active and signal in ("LONG", "SHORT"):
            if pos.in_cooldown():
                mins = int((pos.cooldown_until - time.time()) / 60) + 1
                log.info(f"⏸️  [{symbol}] Cooldown: {mins} dk")
            elif count_open(positions) >= cfg["max_positions"]:
                log.info(f"🔒 [{symbol}] Max pozisyon doldu")
            else:
                amount = calc_amount(ex, symbol, price)
                if amount is None:
                    pass   # calc_amount sebebini logladı (minimum altı → atla)
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
    START_BALANCE = fetch_balance(ex)
    last_refresh  = time.time()
    symbols = cfg["symbols"] or get_symbols(ex, cfg["top_volatile_count"])

    log.info("=" * 54)
    log.info("  🤖 Kripto Futures Bot v10.0")
    log.info(f"  Bakiye     : {START_BALANCE:.2f} USDT")
    log.info(f"  Coinler    : {len(symbols)} coin taranıyor  (max {cfg['max_positions']} pozisyon)")
    log.info(f"  Kaldıraç   : {cfg['leverage']}x")
    log.info(f"  SL/TP      : ×{cfg['atr_sl_mult']} / ×{cfg['atr_tp_mult']}  R:R 1:{cfg['atr_tp_mult']/cfg['atr_sl_mult']:.0f}")
    log.info(f"  Min Koşul  : {cfg['min_conditions']}/6 koşul")
    log.info(f"  ADX Eşiği  : {cfg['adx_threshold']}")
    log.info(f"  Cooldown   : SL={cfg['cooldown_sl_sec']//60}dk  TP={cfg['cooldown_tp_sec']//60}dk")
    log.info(f"  Günlük Lim : %{cfg['daily_loss_pct']}")
    if cfg.get("roi_tp_enabled"):
        log.info(f"  ROI TP     : +%{cfg['roi_tp_pct']*100:.1f} kaldıraçlı kârda anında kapat (aktif)")
    log.info(f"  Mod        : {'🧪 DRY RUN' if cfg['dry_run'] else '💰 CANLI'}")
    log.info("=" * 54)

    positions = {}
    for sym in symbols:
        positions[sym] = Position(sym)
        setup_symbol(ex, sym, cfg["leverage"])
        time.sleep(0.2)

    # Restart mutabakatı — borsadaki açık pozisyonları yükle (çift pozisyonu önler)
    reconcile_positions(ex, positions)

    while True:
        if pnl_tracker.daily_limit_hit(START_BALANCE):
            log.warning("💤 1 saat bekleniyor...")
            time.sleep(3600)
            continue

        if not cfg["symbols"] and time.time() - last_refresh > cfg["symbol_refresh_sec"]:
            log.info("🔄 Semboller yenileniyor...")
            new_syms = get_symbols(ex, cfg["top_volatile_count"])
            for s in new_syms:
                if s not in positions:
                    positions[s] = Position(s)
                    setup_symbol(ex, s, cfg["leverage"])
            symbols      = new_syms
            last_refresh = time.time()

        # BTC korelasyon filtresi için BTC değişimini al
        btc_chg = get_btc_change(ex)
        if CONFIG["btc_filter_enabled"]:
            log.info(f"📊 BTC 1h değişim: {btc_chg*100:+.2f}%  {'🔴 LONG engel' if btc_chg <= -CONFIG['btc_drop_threshold'] else '🟢 SHORT engel' if btc_chg >= CONFIG['btc_pump_threshold'] else '✅ normal'}")

        # Borsadaki gerçek pozisyon durumunu bir kez çek (dış kapanışları yakala)
        live_pos = fetch_live_positions(ex, symbols)

        for sym in symbols:
            run_symbol(ex, sym, positions[sym], positions, btc_chg, live_pos)
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
