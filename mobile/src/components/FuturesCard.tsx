import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { FuturesValue } from '../types';
import { colors, spacing, radius } from '../theme';
import { formatUSD, formatPct, formatQty } from '../utils/format';

export function FuturesCard({
  item,
  onDelete,
}: {
  item: FuturesValue;
  onDelete: (id: string) => void;
}) {
  const { position: p } = item;
  const isLong = p.side === 'long';
  const sideColor = isLong ? colors.green : colors.red;
  const pnlColor = item.pnl >= 0 ? colors.green : colors.red;

  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <View style={styles.symbolRow}>
          <View style={[styles.sideBadge, { backgroundColor: sideColor + '22' }]}>
            <Text style={[styles.sideText, { color: sideColor }]}>
              {isLong ? 'LONG' : 'SHORT'}
            </Text>
          </View>
          <Text style={styles.symbol}>{p.symbol}USDT.P</Text>
          <View style={styles.levBadge}>
            <Text style={styles.levText}>{formatQty(p.leverage)}x</Text>
          </View>
          {item.priceIsLive && <View style={styles.liveDot} />}
        </View>
        <TouchableOpacity onPress={() => onDelete(p.id)} hitSlop={8}>
          <Text style={styles.delete}>Sil</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.pnlRow}>
        <Text style={[styles.pnl, { color: pnlColor }]}>
          {formatUSD(item.pnl)}
        </Text>
        <Text style={[styles.roi, { color: pnlColor }]}>
          {formatPct(item.roiPct)}
        </Text>
      </View>

      <View style={styles.grid}>
        <Detail label="Giriş" value={formatUSD(p.entryPrice)} />
        <Detail label="Güncel" value={formatUSD(item.markPrice)} />
        <Detail label="Teminat" value={formatUSD(p.margin)} />
        <Detail label="Büyüklük" value={formatUSD(item.notional)} />
        <Detail label="Likidasyon" value={formatUSD(item.liqPrice)} danger />
      </View>
    </View>
  );
}

function Detail({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <View style={styles.detail}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, danger && { color: colors.gold }]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  symbolRow: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  sideBadge: {
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginRight: spacing.sm,
  },
  sideText: { fontSize: 10, fontWeight: '800' },
  symbol: { color: colors.text, fontSize: 15, fontWeight: '600' },
  levBadge: {
    backgroundColor: colors.cardAlt,
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: spacing.sm,
  },
  levText: { color: colors.textDim, fontSize: 10, fontWeight: '700' },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.green,
    marginLeft: spacing.sm,
  },
  delete: { color: colors.textDim, fontSize: 11 },
  pnlRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  pnl: { fontSize: 22, fontWeight: '700' },
  roi: { fontSize: 15, fontWeight: '600' },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.md,
    gap: spacing.md,
  },
  detail: { minWidth: '28%' },
  detailLabel: { color: colors.textDim, fontSize: 11 },
  detailValue: { color: colors.text, fontSize: 13, fontWeight: '600', marginTop: 2 },
});
