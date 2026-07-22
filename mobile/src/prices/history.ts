// ─────────────────────────────────────────────────────────────
// Geçmiş fiyat (grafik) verisi — kripto, USD bazında.
// Aralık DAKİKA cinsinden verilir; uygun mum aralığı (1m…1d) seçilir.
// Binance klines (USD) önce; olmazsa CoinGecko market_chart (usd).
// ─────────────────────────────────────────────────────────────

const CG = 'https://api.coingecko.com/api/v3';
const BIN = 'https://api.binance.com/api/v3';

// Toplam dakikaya göre mum aralığı seçimi.
const STEPS: { maxMin: number; interval: string; stepMin: number }[] = [
  { maxMin: 180, interval: '1m', stepMin: 1 },
  { maxMin: 720, interval: '5m', stepMin: 5 },
  { maxMin: 1440, interval: '15m', stepMin: 15 },
  { maxMin: 4320, interval: '1h', stepMin: 60 },
  { maxMin: 20160, interval: '2h', stepMin: 120 },
  { maxMin: 86400, interval: '8h', stepMin: 480 },
  { maxMin: Infinity, interval: '1d', stepMin: 1440 },
];

function pickStep(minutes: number) {
  return STEPS.find((s) => minutes <= s.maxMin) ?? STEPS[STEPS.length - 1];
}

async function binanceKlinesUSD(
  symbol: string,
  minutes: number
): Promise<number[]> {
  const { interval, stepMin } = pickStep(minutes);
  const limit = Math.min(1000, Math.max(2, Math.ceil(minutes / stepMin)));
  const kUrl = `${BIN}/klines?symbol=${symbol}USDT&interval=${interval}&limit=${limit}`;
  const res = await fetch(kUrl);
  if (!res.ok) throw new Error(`Binance ${res.status}`);
  const kl = (await res.json()) as (string | number)[][];
  const out = kl
    .map((k) => parseFloat(String(k[4]))) // close (index 4), USDT ≈ USD
    .filter((x) => isFinite(x));
  if (out.length < 2) throw new Error('Binance geçmiş yok');
  return out;
}

async function coingeckoHistoryUSD(
  coingeckoId: string,
  minutes: number
): Promise<number[]> {
  const days = Math.max(1, Math.ceil(minutes / 1440));
  const url = `${CG}/coins/${encodeURIComponent(
    coingeckoId
  )}/market_chart?vs_currency=usd&days=${days}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const json = (await res.json()) as { prices?: [number, number][] };
  let out = (json.prices ?? []).map((p) => p[1]).filter((x) => isFinite(x));
  // Gün-altı aralıkta CoinGecko tam günü döndürür; son kısmı al.
  if (minutes < 1440 && out.length > 0) {
    out = out.slice(-Math.max(2, Math.ceil(minutes / 5)));
  }
  if (out.length < 2) throw new Error('CoinGecko geçmiş yok');
  return out;
}

// Kripto geçmiş fiyatı — USD bazında. minutes = toplam süre (dakika).
export async function fetchCryptoHistory(
  coingeckoId: string,
  symbol: string,
  minutes: number
): Promise<number[]> {
  try {
    return await binanceKlinesUSD(symbol, minutes);
  } catch (eB: any) {
    try {
      return await coingeckoHistoryUSD(coingeckoId, minutes);
    } catch (eC: any) {
      throw new Error(`${eB?.message ?? 'Binance?'} · ${eC?.message ?? 'CoinGecko?'}`);
    }
  }
}
