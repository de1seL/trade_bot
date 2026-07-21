// Uygulamada seçilebilen popüler kriptolar → CoinGecko id eşlemesi.
// Yeni coin eklemek = buraya bir satır eklemek.
export interface CoinOption {
  symbol: string;
  name: string;
  coingeckoId: string;
}

export const COINS: CoinOption[] = [
  { symbol: 'BTC', name: 'Bitcoin', coingeckoId: 'bitcoin' },
  { symbol: 'ETH', name: 'Ethereum', coingeckoId: 'ethereum' },
  { symbol: 'BNB', name: 'BNB', coingeckoId: 'binancecoin' },
  { symbol: 'SOL', name: 'Solana', coingeckoId: 'solana' },
  { symbol: 'XRP', name: 'XRP', coingeckoId: 'ripple' },
  { symbol: 'ADA', name: 'Cardano', coingeckoId: 'cardano' },
  { symbol: 'AVAX', name: 'Avalanche', coingeckoId: 'avalanche-2' },
  { symbol: 'DOGE', name: 'Dogecoin', coingeckoId: 'dogecoin' },
  { symbol: 'TRX', name: 'TRON', coingeckoId: 'tron' },
  { symbol: 'DOT', name: 'Polkadot', coingeckoId: 'polkadot' },
  { symbol: 'MATIC', name: 'Polygon', coingeckoId: 'matic-network' },
  { symbol: 'LINK', name: 'Chainlink', coingeckoId: 'chainlink' },
  { symbol: 'LTC', name: 'Litecoin', coingeckoId: 'litecoin' },
  { symbol: 'ATOM', name: 'Cosmos', coingeckoId: 'cosmos' },
  { symbol: 'USDT', name: 'Tether', coingeckoId: 'tether' },
];

export function findCoin(coingeckoId: string): CoinOption | undefined {
  return COINS.find((c) => c.coingeckoId === coingeckoId);
}
