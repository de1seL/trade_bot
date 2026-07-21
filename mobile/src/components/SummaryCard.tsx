import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PortfolioSummary } from '../types';
import { colors, spacing, radius } from '../theme';
import { formatTRY, formatPct } from '../utils/format';

export function SummaryCard({ summary }: { summary: PortfolioSummary }) {
  const pnlColor = summary.totalPnl >= 0 ? colors.green : colors.red;
  const realColor = summary.totalRealPnl >= 0 ? colors.green : colors.red;

  return (
    <View style={styles.card}>
      <Text style={styles.label}>Toplam Portföy Değeri</Text>
      <Text style={styles.total}>{formatTRY(summary.totalValue)}</Text>

      <View style={styles.row}>
        <View style={styles.col}>
          <Text style={styles.subLabel}>Nominal K/Z</Text>
          <Text style={[styles.pnl, { color: pnlColor }]}>
            {formatTRY(summary.totalPnl)}
          </Text>
          <Text style={[styles.pnlPct, { color: pnlColor }]}>
            {formatPct(summary.totalPnlPct)}
          </Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.col}>
          <Text style={styles.subLabel}>Reel K/Z (enflasyona göre)</Text>
          <Text style={[styles.pnl, { color: realColor }]}>
            {formatTRY(summary.totalRealPnl)}
          </Text>
          <Text style={[styles.pnlPct, { color: realColor }]}>
            {formatPct(summary.totalRealPnlPct)}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  label: { color: colors.textDim, fontSize: 13 },
  total: {
    color: colors.text,
    fontSize: 34,
    fontWeight: '700',
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  col: { flex: 1 },
  divider: { width: 1, backgroundColor: colors.border, marginHorizontal: spacing.md },
  subLabel: { color: colors.textDim, fontSize: 11, marginBottom: spacing.xs },
  pnl: { fontSize: 17, fontWeight: '600' },
  pnlPct: { fontSize: 13, fontWeight: '500', marginTop: 2 },
});
