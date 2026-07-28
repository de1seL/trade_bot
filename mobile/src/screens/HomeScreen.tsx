import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Currency, FuturesSummary, PortfolioSummary } from '../types';
import { colors, spacing, radius } from '../theme';
import { formatMoney, formatTRY, formatUSD, formatPct, formatQty } from '../utils/format';
import { fetchHomeIndicators, Indicator } from '../prices/home';
import { fetchCryptoMarket } from '../prices/market';
import { fetchStockMarket } from '../prices/stocks';
import { MarketQuote } from '../prices/market';

function fmtIndicator(i: Indicator): string {
  if (i.unit === 'USD') return formatUSD(i.value);
  if (i.unit === 'POINT') return formatQty(i.value);
  return formatTRY(i.value);
}

export function HomeScreen({
  name,
  summary,
  futuresSummary,
  displayCurrency,
  usdTry,
  onOpenSettings,
  onGoMarket,
}: {
  name: string;
  summary: PortfolioSummary;
  futuresSummary: FuturesSummary;
  displayCurrency: Currency;
  usdTry: number | null;
  onOpenSettings: () => void;
  onGoMarket: () => void;
}) {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [coins, setCoins] = useState<MarketQuote[]>([]);
  const [stocks, setStocks] = useState<MarketQuote[]>([]);
  const [popularTab, setPopularTab] = useState<'crypto' | 'stock'>('crypto');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [ind, cr, st] = await Promise.all([
      fetchHomeIndicators().catch(() => []),
      fetchCryptoMarket().catch(() => []),
      fetchStockMarket().catch(() => []),
    ]);
    setIndicators(ind);
    setCoins(cr.slice(0, 6));
    setStocks(st.slice(0, 6));
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Portföy + Futures birleşik toplam (görüntü para biriminde).
  const factor = displayCurrency === 'USD' ? 1 : usdTry ?? 1;
  const futMargin = futuresSummary.totalMargin * factor;
  const futPnl = futuresSummary.totalPnl * factor;
  const totalValue = summary.totalValue + futMargin + futPnl;
  const totalCost = summary.totalCost + futMargin;
  const totalPnl = totalValue - totalCost;
  const totalPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;
  const pnlColor = totalPnl >= 0 ? colors.green : colors.red;

  const popular = popularTab === 'crypto' ? coins : stocks;
  const showUsd = popularTab === 'crypto';

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.textDim} />
      }
    >
      {/* Karşılama */}
      <View style={styles.greetRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.hello}>
            Merhaba{name ? ` ${name}` : ''} 👋
          </Text>
          <Text style={styles.subtitle}>Bugünün özeti</Text>
        </View>
        <TouchableOpacity onPress={onOpenSettings} hitSlop={8}>
          <Text style={styles.settings}>⚙︎</Text>
        </TouchableOpacity>
      </View>

      {/* Günün özeti — birleşik toplam */}
      <View style={styles.summaryCard}>
        <Text style={styles.summaryLabel}>Toplam Varlık (Portföy + Futures)</Text>
        <Text style={styles.summaryTotal}>
          {formatMoney(totalValue, displayCurrency)}
        </Text>
        <View style={styles.pnlRow}>
          <Text style={[styles.pnl, { color: pnlColor }]}>
            {formatMoney(totalPnl, displayCurrency)}
          </Text>
          <View style={[styles.pctPill, { backgroundColor: pnlColor + '22' }]}>
            <Text style={[styles.pctText, { color: pnlColor }]}>
              {formatPct(totalPct)}
            </Text>
          </View>
        </View>
      </View>

      {/* Göstergeler: Dolar / Euro / BIST 100 / Bitcoin */}
      <View style={styles.indGrid}>
        {indicators.length === 0 && loading ? (
          <ActivityIndicator color={colors.textDim} style={{ marginVertical: spacing.lg }} />
        ) : (
          indicators.map((i) => {
            const up = (i.changePct ?? 0) >= 0;
            const c = up ? colors.green : colors.red;
            return (
              <View key={i.key} style={styles.indCard}>
                <Text style={styles.indLabel}>{i.label}</Text>
                <Text style={styles.indValue}>{fmtIndicator(i)}</Text>
                {typeof i.changePct === 'number' && (
                  <Text style={[styles.indChange, { color: c }]}>
                    {formatPct(i.changePct)}
                  </Text>
                )}
              </View>
            );
          })
        )}
      </View>

      {/* Popüler */}
      <View style={styles.popularHeader}>
        <View style={styles.popularToggle}>
          {(['crypto', 'stock'] as const).map((t) => (
            <TouchableOpacity
              key={t}
              onPress={() => setPopularTab(t)}
              style={[styles.popBtn, popularTab === t && styles.popBtnActive]}
            >
              <Text style={[styles.popText, popularTab === t && styles.popTextActive]}>
                {t === 'crypto' ? 'Popüler Coinler' : 'Popüler Hisseler'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <View style={styles.popularList}>
        {popular.length === 0 ? (
          <Text style={styles.emptyHint}>
            {loading ? 'Yükleniyor…' : 'Veri gelmedi, aşağı çekip yenile.'}
          </Text>
        ) : (
          popular.map((q) => {
            const up = q.changePct >= 0;
            const c = up ? colors.green : colors.red;
            return (
              <View key={q.key} style={styles.popRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.popSymbol}>{q.symbol}</Text>
                  <Text style={styles.popName} numberOfLines={1}>
                    {q.name}
                  </Text>
                </View>
                <Text style={styles.popPrice}>
                  {showUsd ? formatUSD(q.priceUsd) : formatTRY(q.priceTry)}
                </Text>
                <Text style={[styles.popChange, { color: c }]}>
                  {formatPct(q.changePct)}
                </Text>
              </View>
            );
          })
        )}
        <TouchableOpacity onPress={onGoMarket} style={styles.allBtn}>
          <Text style={styles.allText}>Piyasa'da tümünü gör →</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: spacing.xl * 2 },
  greetRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.lg },
  hello: { color: colors.text, fontSize: 24, fontWeight: '700' },
  subtitle: { color: colors.textDim, fontSize: 14, marginTop: 2 },
  settings: { color: colors.textDim, fontSize: 22 },
  summaryCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  summaryLabel: { color: colors.textDim, fontSize: 13 },
  summaryTotal: {
    color: colors.text,
    fontSize: 34,
    fontWeight: '700',
    marginTop: spacing.xs,
  },
  pnlRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.md },
  pnl: { fontSize: 16, fontWeight: '600' },
  pctPill: { borderRadius: 20, paddingHorizontal: spacing.md, paddingVertical: 4 },
  pctText: { fontSize: 13, fontWeight: '700' },
  indGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  indCard: {
    flexBasis: '47%',
    flexGrow: 1,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  indLabel: { color: colors.textDim, fontSize: 12 },
  indValue: { color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 4 },
  indChange: { fontSize: 12, fontWeight: '600', marginTop: 2 },
  popularHeader: { marginTop: spacing.xl },
  popularToggle: { flexDirection: 'row', gap: spacing.sm },
  popBtn: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
  },
  popBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  popText: { color: colors.textDim, fontSize: 12, fontWeight: '600' },
  popTextActive: { color: '#fff' },
  popularList: { marginTop: spacing.md },
  popRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.sm,
    gap: spacing.md,
  },
  popSymbol: { color: colors.text, fontSize: 14, fontWeight: '700' },
  popName: { color: colors.textDim, fontSize: 11, marginTop: 2 },
  popPrice: { color: colors.text, fontSize: 13, fontWeight: '600' },
  popChange: { fontSize: 12, fontWeight: '700', minWidth: 68, textAlign: 'right' },
  emptyHint: { color: colors.textDim, fontSize: 13, textAlign: 'center', paddingVertical: spacing.lg },
  allBtn: { alignItems: 'center', paddingVertical: spacing.md },
  allText: { color: colors.primary, fontSize: 13, fontWeight: '600' },
});
