import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { HoldingValue } from '../types';
import { colors, spacing, radius, assetMeta } from '../theme';
import { formatMoney, formatPct, formatQty } from '../utils/format';

export function HoldingCard({
  item,
  onDelete,
}: {
  item: HoldingValue;
  onDelete: (id: string) => void;
}) {
  const { holding } = item;
  const pnlColor = item.pnl >= 0 ? colors.green : colors.red;
  const meta = assetMeta[holding.type];

  return (
    <View style={styles.card}>
      <View style={styles.left}>
        <View style={styles.symbolRow}>
          <View style={[styles.badge, { backgroundColor: (meta?.color ?? colors.textDim) + '22' }]}>
            <Text style={[styles.badgeText, { color: meta?.color ?? colors.textDim }]}>
              {meta?.label ?? holding.type}
            </Text>
          </View>
          <Text style={styles.symbol}>{holding.symbol}</Text>
          {item.priceIsLive && <View style={styles.liveDot} />}
        </View>
        <Text style={styles.sub}>
          {formatQty(holding.quantity)} × {formatMoney(item.currentPrice, item.currency)}
        </Text>
        <Text style={styles.buyInfo}>
          Alış: {holding.buyCurrency} · {formatQty(holding.buyPrice)}
        </Text>
      </View>

      <View style={styles.right}>
        <Text style={styles.value}>{formatMoney(item.value, item.currency)}</Text>
        <Text style={[styles.pnl, { color: pnlColor }]}>
          {formatPct(item.pnlPct)}
        </Text>
        <TouchableOpacity onPress={() => onDelete(holding.id)} hitSlop={8}>
          <Text style={styles.delete}>Sil</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  left: { flex: 1 },
  symbolRow: { flexDirection: 'row', alignItems: 'center' },
  badge: {
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginRight: spacing.sm,
  },
  badgeText: { fontSize: 10, fontWeight: '700' },
  symbol: { color: colors.text, fontSize: 16, fontWeight: '600' },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.green,
    marginLeft: spacing.sm,
  },
  sub: { color: colors.textDim, fontSize: 12, marginTop: 4 },
  buyInfo: { color: colors.textDim, fontSize: 11, marginTop: 2, opacity: 0.8 },
  right: { alignItems: 'flex-end' },
  value: { color: colors.text, fontSize: 15, fontWeight: '600' },
  pnl: { fontSize: 13, marginTop: 2 },
  delete: { color: colors.textDim, fontSize: 11, marginTop: spacing.sm },
});
