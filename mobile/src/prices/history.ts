// ─────────────────────────────────────────────────────────────
// Geçmiş fiyat (grafik) verisi — kripto, USD bazında.
// Binance klines (USD) önce; olmazsa CoinGecko market_chart (usd).
// ─────────────────────────────────────────────────────────────

const CG = 'https://api.coingecko.com/api/v3';
const BIN = 'https://api.binance.com/api/v3';

async function binanceKlinesUSD(
  symbol: string,
  days: number
): Promise<number[]> {
  const interval = days <= 1 ? '15m' : days <= 7 ? '2h' : days <= 30 ? '8h' : '1d';
  const limit =
    days <= 1 ? 96 : days <= 7 ? 84 : days <= 30 ? 90 : Math.min(days, 1000);
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
  days: number
): Promise<number[]> {
  const url = `${CG}/coins/${encodeURIComponent(
    coingeckoId
  )}/market_chart?vs_currency=usd&days=${days}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const json = (await res.json()) as { prices?: [number, number][] };
  const out = (json.prices ?? []).map((p) => p[1]).filter((x) => isFinite(x));
  if (out.length < 2) throw new Error('CoinGecko geçmiş yok');
  return out;
}

// Kripto geçmiş fiyatı — USD bazında.
export async function fetchCryptoHistory(
  coingeckoId: string,
  symbol: string,
  days: number
): Promise<number[]> {
  try {
    return await binanceKlinesUSD(symbol, days);
  } catch (eB: any) {
    try {
      return await coingeckoHistoryUSD(coingeckoId, days);
    } catch (eC: any) {
      throw new Error(`${eB?.message ?? 'Binance?'} · ${eC?.message ?? 'CoinGecko?'}`);
    }
  }
}
