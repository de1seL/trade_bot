import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { FuturesSummary } from '../types';
import { colors, spacing, radius } from '../theme';
import { FuturesCard } from '../components/FuturesCard';
import { formatUSD, formatPct } from '../utils/format';

export function FuturesScreen({
  summary,
  refreshing,
  priceError,
  onRefresh,
  onAdd,
  onDelete,
}: {
  summary: FuturesSummary;
  refreshing: boolean;
  priceError?: string;
  onRefresh: () => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
}) {
  const isEmpty = summary.items.length === 0;
  const pnlColor = summary.totalPnl >= 0 ? colors.green : colors.red;

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <Text style={styles.appTitle}>Futures</Text>
        <Text style={styles.tag}>USDT-M</Text>
      </View>

      <FlatList
        data={summary.items}
        keyExtractor={(i) => i.position.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.textDim}
          />
        }
        ListHeaderComponent={
          <View style={styles.headerBlock}>
            <View style={styles.card}>
              <Text style={styles.label}>Toplam Teminat</Text>
              <Text style={styles.total}>{formatUSD(summary.totalMargin)}</Text>
              <View style={styles.row}>
                <View style={styles.col}>
                  <Text style={styles.subLabel}>Toplam K/Z (USDT)</Text>
                  <Text style={[styles.pnl, { color: pnlColor }]}>
                    {formatUSD(summary.totalPnl)}
                  </Text>
                </View>
                <View style={styles.divider} />
                <View style={styles.col}>
                  <Text style={styles.subLabel}>ROI (teminata göre)</Text>
                  <Text style={[styles.pnl, { color: pnlColor }]}>
                    {formatPct(summary.totalRoiPct)}
                  </Text>
                </View>
              </View>
            </View>
            {!!priceError && (
              <Text style={styles.warn}>
                Canlı fiyat güncellenemedi ({priceError}). Aşağı çekip tekrar
                deneyebilirsin.
              </Text>
            )}
            {!isEmpty && <Text style={styles.sectionTitle}>Pozisyonlar</Text>}
          </View>
        }
        renderItem={({ item }) => (
          <View style={{ marginBottom: spacing.md }}>
            <FuturesCard item={item} onDelete={onDelete} />
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Henüz pozisyon yok</Text>
            <Text style={styles.emptyText}>
              + ile ilk futures pozisyonunu ekle: coin, yön (long/short), giriş
              fiyatı, kaldıraç ve teminat. K/Z, ROI ve tahmini likidasyon fiyatı
              otomatik hesaplanır.
            </Text>
          </View>
        }
      />

      <TouchableOpacity style={styles.fab} onPress={onAdd} activeOpacity={0.85}>
        <Text style={styles.fabText}>＋</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  appTitle: { color: colors.text, fontSize: 22, fontWeight: '700' },
  tag: {
    color: colors.gold,
    fontSize: 11,
    fontWeight: '700',
    borderWidth: 1,
    borderColor: colors.gold + '55',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  list: { padding: spacing.lg, paddingTop: 0, paddingBottom: 120 },
  headerBlock: { marginBottom: spacing.md },
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
    fontSize: 30,
    fontWeight: '700',
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  col: { flex: 1 },
  divider: { width: 1, backgroundColor: colors.border, marginHorizontal: spacing.md },
  subLabel: { color: colors.textDim, fontSize: 11, marginBottom: spacing.xs },
  pnl: { fontSize: 17, fontWeight: '600' },
  sectionTitle: {
    color: colors.textDim,
    fontSize: 13,
    fontWeight: '600',
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  warn: { color: colors.gold, fontSize: 12, marginTop: spacing.md, lineHeight: 17 },
  empty: { alignItems: 'center', paddingTop: spacing.xl * 2 },
  emptyTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '600',
    marginBottom: spacing.sm,
  },
  emptyText: {
    color: colors.textDim,
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
    paddingHorizontal: spacing.lg,
  },
  fab: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl,
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 6,
  },
  fabText: { color: '#fff', fontSize: 30, marginTop: -2 },
});
