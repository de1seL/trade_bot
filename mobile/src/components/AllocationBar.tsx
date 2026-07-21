import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { HoldingValue } from '../types';
import { colors, spacing, radius, assetMeta } from '../theme';
import { allocationByType } from '../utils/portfolio';
import { formatPct } from '../utils/format';

export function AllocationBar({ items }: { items: HoldingValue[] }) {
  const alloc = allocationByType(items);
  if (alloc.length === 0) return null;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Dağılım</Text>
      <View style={styles.bar}>
        {alloc.map((a) => (
          <View
            key={a.type}
            style={{
              width: `${a.pct}%`,
              backgroundColor: assetMeta[a.type]?.color ?? colors.textDim,
            }}
          />
        ))}
      </View>
      <View style={styles.legend}>
        {alloc.map((a) => (
          <View key={a.type} style={styles.legendItem}>
            <View
              style={[
                styles.dot,
                { backgroundColor: assetMeta[a.type]?.color ?? colors.textDim },
              ]}
            />
            <Text style={styles.legendText}>
              {assetMeta[a.type]?.label ?? a.type} {formatPct(a.pct).replace('+', '')}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { color: colors.textDim, fontSize: 13, marginBottom: spacing.md },
  bar: {
    flexDirection: 'row',
    height: 14,
    borderRadius: 7,
    overflow: 'hidden',
    backgroundColor: colors.cardAlt,
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.md,
    gap: spacing.md,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  legendText: { color: colors.text, fontSize: 12 },
});
