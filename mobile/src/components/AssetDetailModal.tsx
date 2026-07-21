import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { colors, spacing, radius } from '../theme';
import { formatTRY, formatPct } from '../utils/format';
import { MarketQuote } from '../prices/market';
import { fetchCryptoHistory } from '../prices/history';
import { fetchStockHistory } from '../prices/stocks';
import { LineChart } from './LineChart';

type Kind = 'crypto' | 'stock';

const RANGES: { label: string; days: number }[] = [
  { label: '1G', days: 1 },
  { label: '1H', days: 7 },
  { label: '1A', days: 30 },
  { label: '1Y', days: 365 },
];

export function AssetDetailModal({
  visible,
  kind,
  quote,
  onClose,
}: {
  visible: boolean;
  kind: Kind;
  quote: MarketQuote | null;
  onClose: () => void;
}) {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!visible || !quote) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const series =
          kind === 'crypto'
            ? await fetchCryptoHistory(quote.key, quote.symbol, days)
            : await fetchStockHistory(quote.symbol, days);
        if (!cancelled) setData(series);
      } catch (e: any) {
        if (!cancelled) {
          setData([]);
          setError(`Grafik alınamadı — ${e?.message ?? 'ağ'}`);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [visible, quote, kind, days]);

  const chartWidth = Dimensions.get('window').width - spacing.lg * 2;
  const up = quote ? quote.changePct >= 0 : true;
  const changeColor = up ? colors.green : colors.red;

  // Kripto: 1G/1H/1A. Hisse: 1H/1A/1Y.
  const ranges = kind === 'crypto' ? RANGES.slice(0, 3) : RANGES.slice(1);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={styles.container}>
        <View style={styles.header}>
          <View>
            <Text style={styles.symbol}>{quote?.symbol}</Text>
            <Text style={styles.name}>{quote?.name}</Text>
          </View>
          <TouchableOpacity onPress={onClose} hitSlop={8}>
            <Text style={styles.close}>Kapat</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.priceRow}>
          <Text style={styles.price}>
            {quote ? formatTRY(quote.priceTry) : '-'}
          </Text>
          <Text style={[styles.change, { color: changeColor }]}>
            {quote ? formatPct(quote.changePct) : ''}
          </Text>
        </View>

        <View style={styles.chartBox}>
          {loading ? (
            <ActivityIndicator color={colors.textDim} />
          ) : error ? (
            <Text style={styles.error}>{error}</Text>
          ) : (
            <LineChart data={data} width={chartWidth} height={220} />
          )}
        </View>

        <View style={styles.rangeRow}>
          {ranges.map((r) => (
            <TouchableOpacity
              key={r.days}
              onPress={() => setDays(r.days)}
              style={[styles.rangeBtn, days === r.days && styles.rangeBtnActive]}
            >
              <Text
                style={[
                  styles.rangeText,
                  days === r.days && styles.rangeTextActive,
                ]}
              >
                {r.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.note}>
          Grafik {kind === 'crypto' ? 'Binance/CoinGecko' : 'Yahoo Finance'}{' '}
          verisiyle, TL bazında.
        </Text>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: spacing.lg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginTop: spacing.sm,
  },
  symbol: { color: colors.text, fontSize: 22, fontWeight: '700' },
  name: { color: colors.textDim, fontSize: 13, marginTop: 2 },
  close: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  price: { color: colors.text, fontSize: 26, fontWeight: '700' },
  change: { fontSize: 16, fontWeight: '600' },
  chartBox: {
    height: 230,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  error: { color: colors.gold, fontSize: 13, textAlign: 'center' },
  rangeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xl,
  },
  rangeBtn: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
  },
  rangeBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  rangeText: { color: colors.textDim, fontSize: 13, fontWeight: '700' },
  rangeTextActive: { color: '#fff' },
  note: { color: colors.textDim, fontSize: 11, marginTop: spacing.lg },
});
