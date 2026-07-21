import { CoinOption } from './coins';

// ─────────────────────────────────────────────────────────────
// Coin arama — CoinGecko /search ile binlerce coin arasında ara.
// Kullanıcı "pepe", "render" vb. yazınca eşleşen coin'leri döndürür.
// ─────────────────────────────────────────────────────────────

const SEARCH_URL = 'https://api.coingecko.com/api/v3/search';

export async function searchCoins(query: string): Promise<CoinOption[]> {
  const q = query.trim();
  if (q.length < 2) return [];
  const url = `${SEARCH_URL}?query=${encodeURIComponent(q)}`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const data = (await res.json()) as {
    coins?: { id: string; symbol: string; name: string }[];
  };
  const coins = data.coins ?? [];
  return coins.slice(0, 25).map((c) => ({
    symbol: c.symbol.toUpperCase(),
    name: c.name,
    coingeckoId: c.id,
  }));
}
