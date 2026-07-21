import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ActivityIndicator,
  Dimensions,
  TextInput,
} from 'react-native';
import { colors, spacing, radius } from '../theme';
import { formatTRY, formatUSD, formatPct } from '../utils/format';
import { MarketQuote } from '../prices/market';
import { fetchCryptoHistory } from '../prices/history';
import { fetchStockHistory } from '../prices/stocks';
import { LineChart } from './LineChart';

type Kind = 'crypto' | 'stock';

const RANGES: { label: string; days: number }[] = [
  { label: '1G', days: 1 },
  { label: '1H', days: 7 },
  { label: '1A', days: 30 },
  { label: '3A', days: 90 },
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
  const [showCustom, setShowCustom] = useState(false);
  const [customText, setCustomText] = useState('');

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

  // Kripto: 1G'den; Hisse: 1H'den (borsa gün içi yok).
  const ranges = kind === 'crypto' ? RANGES : RANGES.slice(1);
  const isPreset = ranges.some((r) => r.days === days);

  function applyCustom() {
    const n = Math.round(parseFloat(customText.replace(',', '.')));
    if (!isNaN(n) && n >= 1) {
      setDays(Math.min(n, 1825)); // en fazla ~5 yıl
      setShowCustom(false);
    }
  }

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
            {quote
              ? kind === 'crypto'
                ? formatUSD(quote.priceUsd)
                : formatTRY(quote.priceTry)
              : '-'}
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
              onPress={() => {
                setShowCustom(false);
                setDays(r.days);
              }}
              style={[styles.rangeBtn, days === r.days && styles.rangeBtnActive]}
            >
              <Text
                style={[styles.rangeText, days === r.days && styles.rangeTextActive]}
              >
                {r.label}
              </Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity
            onPress={() => setShowCustom((s) => !s)}
            style={[styles.rangeBtn, (showCustom || !isPreset) && styles.rangeBtnActive]}
          >
            <Text
              style={[
                styles.rangeText,
                (showCustom || !isPreset) && styles.rangeTextActive,
              ]}
            >
              {!isPreset ? `${days}G` : 'Özel'}
            </Text>
          </TouchableOpacity>
        </View>

        {showCustom && (
          <View style={styles.customRow}>
            <TextInput
              style={styles.customInput}
              placeholder="Kaç gün? (örn. 14)"
              placeholderTextColor={colors.textDim}
              value={customText}
              onChangeText={setCustomText}
              keyboardType="number-pad"
              onSubmitEditing={applyCustom}
            />
            <TouchableOpacity style={styles.customApply} onPress={applyCustom}>
              <Text style={styles.customApplyText}>Uygula</Text>
            </TouchableOpacity>
          </View>
        )}

        <Text style={styles.note}>
          Grafik {kind === 'crypto' ? 'Binance/CoinGecko' : 'Yahoo Finance'}{' '}
          verisiyle, {kind === 'crypto' ? 'USD' : 'TL'} bazında.
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
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.xl,
  },
  rangeBtn: {
    minWidth: 52,
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  rangeBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  rangeText: { color: colors.textDim, fontSize: 13, fontWeight: '700' },
  rangeTextActive: { color: '#fff' },
  customRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  customInput: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: 15,
  },
  customApply: {
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.lg,
    justifyContent: 'center',
  },
  customApplyText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  note: { color: colors.textDim, fontSize: 11, marginTop: spacing.lg },
});
