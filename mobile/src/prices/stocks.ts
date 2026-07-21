import { MarketQuote } from './market';
import { BIST } from './bist';

// ─────────────────────────────────────────────────────────────
// BIST hisse verisi — Yahoo Finance (resmi olmayan, anahtarsız uç noktalar).
// Semboller ".IS" ile biter (örn. THYAO.IS). Fiyatlar TL cinsinden.
//
// Not: Yahoo resmi bir API değil; bazı ağlarda engellenebilir/limitlenebilir.
// ─────────────────────────────────────────────────────────────

const YQ = 'https://query1.finance.yahoo.com';
const UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15';

export interface StockRef {
  symbol: string; // görünen sembol (THYAO)
  fullSymbol: string; // Yahoo sembolü (THYAO.IS)
  name: string;
}

const POPULAR_BIST: { symbol: string; name: string }[] = [
  { symbol: 'THYAO', name: 'Türk Hava Yolları' },
  { symbol: 'ASELS', name: 'Aselsan' },
  { symbol: 'GARAN', name: 'Garanti BBVA' },
  { symbol: 'AKBNK', name: 'Akbank' },
  { symbol: 'EREGL', name: 'Ereğli Demir Çelik' },
  { symbol: 'KCHOL', name: 'Koç Holding' },
  { symbol: 'SISE', name: 'Şişecam' },
  { symbol: 'TUPRS', name: 'Tüpraş' },
  { symbol: 'BIMAS', name: 'BİM' },
  { symbol: 'SASA', name: 'Sasa Polyester' },
];

// Tek bir hissenin fiyatı + günlük değişimi (Yahoo v8 chart).
async function fetchChart(
  fullSymbol: string
): Promise<{ price: number; change: number }> {
  const url = `${YQ}/v8/finance/chart/${encodeURIComponent(
    fullSymbol
  )}?interval=1d&range=1d`;
  const res = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': UA },
  });
  if (!res.ok) throw new Error(`Yahoo ${res.status}`);
  const json = (await res.json()) as {
    chart?: {
      result?: {
        meta?: {
          regularMarketPrice?: number;
          previousClose?: number;
          chartPreviousClose?: number;
        };
      }[];
    };
  };
  const meta = json.chart?.result?.[0]?.meta;
  const price = meta?.regularMarketPrice;
  const prev = meta?.previousClose ?? meta?.chartPreviousClose;
  if (typeof price !== 'number') throw new Error('Yahoo fiyat yok');
  const change = prev && prev > 0 ? ((price - prev) / prev) * 100 : 0;
  return { price, change };
}

function toQuote(
  ref: { symbol: string; name: string },
  price: number,
  change: number
): MarketQuote {
  return {
    key: ref.symbol,
    symbol: ref.symbol,
    name: ref.name,
    priceTry: price,
    priceUsd: 0, // hisse: USD gösterilmez
    changePct: change,
  };
}

async function quotesFor(
  refs: { symbol: string; name: string; fullSymbol: string }[]
): Promise<MarketQuote[]> {
  const settled = await Promise.allSettled(
    refs.map((r) => fetchChart(r.fullSymbol))
  );
  const out: MarketQuote[] = [];
  settled.forEach((s, i) => {
    if (s.status === 'fulfilled') {
      out.push(toQuote(refs[i], s.value.price, s.value.change));
    }
  });
  return out;
}

// Popüler BIST hisseleri (arama boşken).
export async function fetchStockMarket(): Promise<MarketQuote[]> {
  const refs = POPULAR_BIST.map((s) => ({ ...s, fullSymbol: `${s.symbol}.IS` }));
  const quotes = await quotesFor(refs);
  if (quotes.length === 0) throw new Error('Yahoo verisi alınamadı');
  return quotes;
}

// BIST hisse arama.
// Önce yerel liste (sembol veya ada göre, Türkçe uyumlu); yerel sonuç yoksa
// Yahoo aramasına düşer. Böylece "GA" → GARAN, "garanti" → GARAN çalışır.
export async function searchStocks(query: string): Promise<StockRef[]> {
  const q = query.trim();
  if (q.length < 1) return [];
  const qUpper = q.toLocaleUpperCase('tr-TR');
  const qLower = q.toLocaleLowerCase('tr-TR');

  const local = BIST.filter(
    (s) =>
      s.symbol.startsWith(qUpper) ||
      s.name.toLocaleLowerCase('tr-TR').includes(qLower)
  )
    .slice(0, 15)
    .map((s) => ({
      symbol: s.symbol,
      fullSymbol: `${s.symbol}.IS`,
      name: s.name,
    }));

  if (local.length > 0) return local;
  try {
    return await yahooSearch(q);
  } catch {
    return [];
  }
}

// Yahoo v1 search (yedek — yerel listede olmayan semboller için).
async function yahooSearch(q: string): Promise<StockRef[]> {
  const url = `${YQ}/v1/finance/search?q=${encodeURIComponent(q)}&lang=tr-TR`;
  const res = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': UA },
  });
  if (!res.ok) throw new Error(`Yahoo ${res.status}`);
  const json = (await res.json()) as {
    quotes?: {
      symbol?: string;
      shortname?: string;
      longname?: string;
      quoteType?: string;
    }[];
  };
  const quotes = json.quotes ?? [];
  return quotes
    .filter(
      (x) =>
        x.symbol &&
        x.symbol.endsWith('.IS') &&
        (x.quoteType === 'EQUITY' || x.quoteType === 'ETF')
    )
    .slice(0, 15)
    .map((x) => ({
      symbol: (x.symbol as string).replace('.IS', ''),
      fullSymbol: x.symbol as string,
      name: x.shortname || x.longname || (x.symbol as string),
    }));
}

// Aranan hisselerin fiyatları.
export async function fetchStockQuotes(refs: StockRef[]): Promise<MarketQuote[]> {
  return quotesFor(refs);
}

// Hisse geçmiş fiyatı (grafik) — Yahoo v8 chart, TL kapanışlar.
export async function fetchStockHistory(
  symbol: string,
  days: number
): Promise<number[]> {
  const fullSymbol = symbol.endsWith('.IS') ? symbol : `${symbol}.IS`;
  const range =
    days <= 7
      ? '5d'
      : days <= 30
      ? '1mo'
      : days <= 90
      ? '3mo'
      : days <= 180
      ? '6mo'
      : days <= 365
      ? '1y'
      : days <= 730
      ? '2y'
      : '5y';
  const interval = days <= 7 ? '60m' : '1d';
  const url = `${YQ}/v8/finance/chart/${encodeURIComponent(
    fullSymbol
  )}?range=${range}&interval=${interval}`;
  const res = await fetch(url, {
    headers: { Accept: 'application/json', 'User-Agent': UA },
  });
  if (!res.ok) throw new Error(`Yahoo ${res.status}`);
  const json = (await res.json()) as {
    chart?: {
      result?: {
        indicators?: { quote?: { close?: (number | null)[] }[] };
      }[];
    };
  };
  const closes = json.chart?.result?.[0]?.indicators?.quote?.[0]?.close ?? [];
  const out = closes.filter((x): x is number => typeof x === 'number');
  if (out.length < 2) throw new Error('Yahoo geçmiş yok');
  return out;
}
