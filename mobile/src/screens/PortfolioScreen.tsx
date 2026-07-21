import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { PortfolioSummary } from '../types';
import { colors, spacing } from '../theme';
import { SummaryCard } from '../components/SummaryCard';
import { AllocationBar } from '../components/AllocationBar';
import { HoldingCard } from '../components/HoldingCard';

export function PortfolioScreen({
  summary,
  refreshing,
  priceError,
  onRefresh,
  onAdd,
  onDelete,
  onOpenSettings,
}: {
  summary: PortfolioSummary;
  refreshing: boolean;
  priceError?: string;
  onRefresh: () => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
}) {
  const isEmpty = summary.items.length === 0;

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <Text style={styles.appTitle}>Portföyüm</Text>
        <TouchableOpacity onPress={onOpenSettings} hitSlop={8}>
          <Text style={styles.settings}>⚙︎</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={summary.items}
        keyExtractor={(i) => i.holding.id}
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
            <SummaryCard summary={summary} />
            {!!priceError && (
              <Text style={styles.warn}>
                Canlı fiyat güncellenemedi ({priceError}). Aşağı çekip tekrar
                deneyebilirsin.
              </Text>
            )}
            {!isEmpty && (
              <View style={{ marginTop: spacing.lg }}>
                <AllocationBar items={summary.items} />
              </View>
            )}
            {!isEmpty && <Text style={styles.sectionTitle}>Varlıklar</Text>}
          </View>
        }
        renderItem={({ item }) => (
          <View style={{ marginBottom: spacing.md }}>
            <HoldingCard item={item} onDelete={onDelete} />
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Henüz varlık yok</Text>
            <Text style={styles.emptyText}>
              Aşağıdaki + düğmesiyle ilk yatırımını ekle. Kriptolar canlı
              fiyatla; hisse, altın ve döviz elle girdiğin fiyatla takip edilir.
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
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  appTitle: { color: colors.text, fontSize: 22, fontWeight: '700' },
  settings: { color: colors.textDim, fontSize: 22 },
  list: { padding: spacing.lg, paddingTop: 0, paddingBottom: 120 },
  headerBlock: { marginBottom: spacing.md },
  sectionTitle: {
    color: colors.textDim,
    fontSize: 13,
    fontWeight: '600',
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  warn: {
    color: colors.gold,
    fontSize: 12,
    marginTop: spacing.md,
    lineHeight: 17,
  },
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
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  fabText: { color: '#fff', fontSize: 30, marginTop: -2 },
});
