// ─────────────────────────────────────────────────────────────
// Geçmiş fiyat (grafik) verisi — kripto.
// Binance klines (USD × USDT/TRY) önce; olmazsa CoinGecko market_chart (TL).
// ─────────────────────────────────────────────────────────────

const CG = 'https://api.coingecko.com/api/v3';
const BIN = 'https://api.binance.com/api/v3';

async function binanceKlinesTRY(
  symbol: string,
  days: number
): Promise<number[]> {
  const interval = days <= 1 ? '15m' : days <= 7 ? '2h' : days <= 30 ? '8h' : '1d';
  const limit = days <= 1 ? 96 : days <= 7 ? 84 : days <= 30 ? 90 : Math.min(days, 365);
  const kUrl = `${BIN}/klines?symbol=${symbol}USDT&interval=${interval}&limit=${limit}`;
  const [kRes, rRes] = await Promise.all([
    fetch(kUrl),
    fetch(`${BIN}/ticker/price?symbol=USDTTRY`),
  ]);
  if (!kRes.ok) throw new Error(`Binance ${kRes.status}`);
  const kl = (await kRes.json()) as (string | number)[][];
  let usdtry = 1;
  if (rRes.ok) {
    const r = (await rRes.json()) as { price?: string };
    usdtry = parseFloat(r.price ?? '1') || 1;
  }
  const out = kl
    .map((k) => parseFloat(String(k[4])) * usdtry) // close (index 4)
    .filter((x) => isFinite(x));
  if (out.length < 2) throw new Error('Binance geçmiş yok');
  return out;
}

async function coingeckoHistoryTRY(
  coingeckoId: string,
  days: number
): Promise<number[]> {
  const url = `${CG}/coins/${encodeURIComponent(
    coingeckoId
  )}/market_chart?vs_currency=try&days=${days}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const json = (await res.json()) as { prices?: [number, number][] };
  const out = (json.prices ?? []).map((p) => p[1]).filter((x) => isFinite(x));
  if (out.length < 2) throw new Error('CoinGecko geçmiş yok');
  return out;
}

export async function fetchCryptoHistory(
  coingeckoId: string,
  symbol: string,
  days: number
): Promise<number[]> {
  try {
    return await binanceKlinesTRY(symbol, days);
  } catch (eB: any) {
    try {
      return await coingeckoHistoryTRY(coingeckoId, days);
    } catch (eC: any) {
      throw new Error(`${eB?.message ?? 'Binance?'} · ${eC?.message ?? 'CoinGecko?'}`);
    }
  }
}
