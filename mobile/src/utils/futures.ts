import {
  FuturesPosition,
  FuturesSummary,
  FuturesValue,
  PricePair,
} from '../types';

// ─────────────────────────────────────────────────────────────
// Futures (USDT-M) pozisyon hesabı — hepsi USDT bazında.
//
//   notional (pozisyon büyüklüğü) = teminat × kaldıraç
//   adet                          = notional / giriş fiyatı
//   K/Z (long)                    = adet × (güncel − giriş)
//   K/Z (short)                   = adet × (giriş − güncel)
//   ROI (teminata göre)           = K/Z / teminat  → kaldıraçlı getiri
//   Likidasyon (yaklaşık, izole, komisyon/bakım marjı hariç):
//     long  ≈ giriş × (1 − 1/kaldıraç)
//     short ≈ giriş × (1 + 1/kaldıraç)
// ─────────────────────────────────────────────────────────────

export function computeFutures(
  pos: FuturesPosition,
  priceMap: Record<string, PricePair>
): FuturesValue {
  const pair = priceMap[pos.coingeckoId];
  const priceIsLive = !!pair && isFinite(pair.usd) && pair.usd > 0;
  const markPrice = priceIsLive ? pair!.usd : pos.entryPrice;

  const notional = pos.margin * pos.leverage;
  const quantity = pos.entryPrice > 0 ? notional / pos.entryPrice : 0;

  const dir = pos.side === 'long' ? 1 : -1;
  const pnl = quantity * (markPrice - pos.entryPrice) * dir;
  const roiPct = pos.margin > 0 ? (pnl / pos.margin) * 100 : 0;

  const liqPrice =
    pos.leverage > 0
      ? pos.side === 'long'
        ? pos.entryPrice * (1 - 1 / pos.leverage)
        : pos.entryPrice * (1 + 1 / pos.leverage)
      : 0;

  return {
    position: pos,
    markPrice,
    notional,
    quantity,
    pnl,
    roiPct,
    liqPrice,
    priceIsLive,
  };
}

export function buildFuturesSummary(
  positions: FuturesPosition[],
  priceMap: Record<string, PricePair>
): FuturesSummary {
  const items = positions.map((p) => computeFutures(p, priceMap));
  const totalMargin = items.reduce((s, i) => s + i.position.margin, 0);
  const totalPnl = items.reduce((s, i) => s + i.pnl, 0);
  const totalRoiPct = totalMargin > 0 ? (totalPnl / totalMargin) * 100 : 0;
  return { totalMargin, totalPnl, totalRoiPct, items };
}
