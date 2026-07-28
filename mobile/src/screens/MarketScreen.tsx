import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { colors, spacing, radius } from '../theme';
import { formatTRY, formatUSD, formatPct } from '../utils/format';
import {
  MarketQuote,
  fetchCryptoMarket,
  fetchGoldMarket,
  fetchQuotesForCoins,
} from '../prices/market';
import { searchCoins } from '../prices/search';
import { fetchStockMarket, searchStocks, fetchStockQuotes } from '../prices/stocks';
import { AssetDetailModal } from '../components/AssetDetailModal';
import { AddPrefill } from './AddHoldingScreen';
import { PriceAlert } from '../types';

type Category = 'crypto' | 'stock' | 'gold' | 'silver';

const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'crypto', label: 'Kripto' },
  { key: 'stock', label: 'Hisse' },
  { key: 'gold', label: 'Altın' },
  { key: 'silver', label: 'Gümüş' },
];

export function MarketScreen({
  onAddToPortfolio,
  alerts,
  onCreateAlert,
  onDeleteAlert,
}: {
  onAddToPortfolio: (p: AddPrefill) => void;
  alerts: PriceAlert[];
  onCreateAlert: (a: PriceAlert) => void;
  onDeleteAlert: (id: string) => void;
}) {
  const [category, setCategory] = useState<Category>('crypto');
  const [quotes, setQuotes] = useState<MarketQuote[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Kripto araması
  const [query, setQuery] = useState('');
  const [searchQuotes, setSearchQuotes] = useState<MarketQuote[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  // Detay/grafik modalı
  const [selected, setSelected] = useState<MarketQuote | null>(null);
  const [selectedKind, setSelectedKind] = useState<'crypto' | 'stock'>('crypto');

  const openDetail = (q: MarketQuote) => {
    setSelectedKind(category === 'stock' ? 'stock' : 'crypto');
    setSelected(q);
  };

  const addSelectedToPortfolio = () => {
    if (!selected) return;
    if (selectedKind === 'crypto') {
      onAddToPortfolio({
        type: 'crypto',
        coin: {
          symbol: selected.symbol,
          name: selected.name,
          coingeckoId: selected.key,
        },
      });
    } else {
      onAddToPortfolio({
        type: 'stock',
        stock: {
          symbol: selected.symbol,
          fullSymbol: `${selected.symbol}.IS`,
          name: selected.name,
        },
      });
    }
    setSelected(null);
  };

  const load = useCallback(async (cat: Category) => {
    if (cat === 'silver') {
      setQuotes([]);
      setError('');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data =
        cat === 'crypto'
          ? await fetchCryptoMarket()
          : cat === 'gold'
          ? await fetchGoldMarket()
          : await fetchStockMarket();
      setQuotes(data);
      if (data.length === 0) setError('Veri gelmedi, tekrar dene');
    } catch (e: any) {
      setError(`Fiyatlar alınamadı — ${e?.message ?? 'ağ hatası'} (aşağı çekip tekrar dene)`);
      setQuotes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(category);
  }, [category, load]);

  // Arama (kripto & hisse): yaz → ilgili kaynakta bul → fiyatlarını getir.
  useEffect(() => {
    if (category !== 'crypto' && category !== 'stock') return;
    const q = query.trim();
    if (q.length < 2) {
      setSearchQuotes([]);
      setSearchError('');
      return;
    }
    let cancelled = false;
    setSearchLoading(true);
    const t = setTimeout(async () => {
      try {
        let data: MarketQuote[];
        if (category === 'crypto') {
          const coins = await searchCoins(q);
          data = await fetchQuotesForCoins(coins.slice(0, 12));
        } else {
          const stocks = await searchStocks(q);
          data = await fetchStockQuotes(stocks.slice(0, 12));
        }
        if (!cancelled) {
          setSearchQuotes(data);
          setSearchError(data.length === 0 ? 'Sonuç/fiyat yok' : '');
        }
      } catch (e: any) {
        if (!cancelled) setSearchError(`Arama başarısız — ${e?.message ?? 'ağ'}`);
      } finally {
        if (!cancelled) setSearchLoading(false);
      }
    }, 450);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, category]);

  const canSearch = category === 'crypto' || category === 'stock';
  const comingSoon = category === 'silver';
  const searching = canSearch && query.trim().length >= 2;
  const data = searching ? searchQuotes : quotes;

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <Text style={styles.appTitle}>Piyasa</Text>
      </View>

      {/* Kategori alt sekmeleri */}
      <View style={styles.catRow}>
        {CATEGORIES.map((c) => (
          <TouchableOpacity
            key={c.key}
            onPress={() => setCategory(c.key)}
            style={[styles.catChip, category === c.key && styles.catChipActive]}
          >
            <Text style={[styles.catText, category === c.key && styles.catTextActive]}>
              {c.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Arama kutusu (kripto & hisse) */}
      {canSearch && (
        <View style={styles.searchWrap}>
          <TextInput
            style={styles.search}
            placeholder={
              category === 'crypto'
                ? 'Coin ara (pepe, render, sui…)'
                : 'Hisse ara (THYAO, ASELS, garanti…)'
            }
            placeholderTextColor={colors.textDim}
            value={query}
            onChangeText={setQuery}
            autoCapitalize={category === 'stock' ? 'characters' : 'none'}
            autoCorrect={false}
          />
          {searchLoading && (
            <ActivityIndicator color={colors.textDim} style={styles.searchSpin} />
          )}
        </View>
      )}

      {comingSoon ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Gümüş verisi yakında</Text>
          <Text style={styles.emptyText}>
            Gümüş için canlı fiyat kaynağı henüz bağlanmadı. Kripto, altın ve
            hisse (BIST) şu an canlı; gümüş bir sonraki adımda eklenecek.
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(q) => q.key}
          contentContainerStyle={styles.list}
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl
              refreshing={loading}
              onRefresh={() => load(category)}
              tintColor={colors.textDim}
            />
          }
          ListHeaderComponent={
            searching && !!searchError ? (
              <Text style={styles.warn}>{searchError}</Text>
            ) : !searching && !!error ? (
              <Text style={styles.warn}>{error}</Text>
            ) : null
          }
          ListEmptyComponent={
            (searching ? searchLoading : loading) ? (
              <ActivityIndicator style={{ marginTop: 40 }} color={colors.textDim} />
            ) : null
          }
          renderItem={({ item }) => (
            <QuoteRow
              item={item}
              primaryUsd={category === 'crypto'}
              onPress={category === 'gold' ? undefined : () => openDetail(item)}
            />
          )}
        />
      )}

      <AssetDetailModal
        visible={!!selected}
        kind={selectedKind}
        quote={selected}
        onClose={() => setSelected(null)}
        onAddToPortfolio={addSelectedToPortfolio}
        alerts={
          selected
            ? alerts.filter(
                (a) => a.kind === selectedKind && a.symbol === selected.symbol
              )
            : []
        }
        onCreateAlert={(target, direction) => {
          if (!selected) return;
          onCreateAlert({
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            kind: selectedKind,
            symbol: selected.symbol,
            name: selected.name,
            coingeckoId: selectedKind === 'crypto' ? selected.key : undefined,
            target,
            direction,
            currency: selectedKind === 'crypto' ? 'USD' : 'TRY',
          });
        }}
        onDeleteAlert={onDeleteAlert}
      />
    </View>
  );
}

function QuoteRow({
  item,
  primaryUsd,
  onPress,
}: {
  item: MarketQuote;
  primaryUsd?: boolean;
  onPress?: () => void;
}) {
  const up = item.changePct >= 0;
  const color = up ? colors.green : colors.red;
  // Kripto → USD ana; hisse/altın → TL ana.
  const primary =
    primaryUsd && item.priceUsd > 0
      ? formatUSD(item.priceUsd)
      : formatTRY(item.priceTry);
  const secondary =
    primaryUsd && item.priceUsd > 0
      ? item.priceTry > 0
        ? formatTRY(item.priceTry)
        : null
      : item.priceUsd > 0
      ? formatUSD(item.priceUsd)
      : null;
  const inner = (
    <>
      <View style={{ flex: 1 }}>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={styles.name} numberOfLines={1}>
          {item.name}
        </Text>
      </View>
      <View style={styles.rightCol}>
        <Text style={styles.priceTry}>{primary}</Text>
        {secondary && <Text style={styles.priceUsd}>{secondary}</Text>}
      </View>
      <View style={styles.changeCol}>
        <Text style={[styles.change, { color }]}>{formatPct(item.changePct)}</Text>
      </View>
      {onPress && <Text style={styles.chevron}>›</Text>}
    </>
  );
  return onPress ? (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.7}>
      {inner}
    </TouchableOpacity>
  ) : (
    <View style={styles.row}>{inner}</View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  topBar: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  appTitle: { color: colors.text, fontSize: 22, fontWeight: '700' },
  catRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  catChip: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
  },
  catChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  catText: { color: colors.textDim, fontSize: 13, fontWeight: '600' },
  catTextActive: { color: '#fff' },
  searchWrap: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    justifyContent: 'center',
  },
  search: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    fontSize: 15,
  },
  searchSpin: { position: 'absolute', right: spacing.xl, top: spacing.md },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
  warn: { color: colors.gold, fontSize: 12, marginBottom: spacing.md },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.sm,
  },
  symbol: { color: colors.text, fontSize: 15, fontWeight: '700' },
  name: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  rightCol: { alignItems: 'flex-end', marginRight: spacing.lg },
  priceTry: { color: colors.text, fontSize: 14, fontWeight: '600' },
  priceUsd: { color: colors.textDim, fontSize: 11, marginTop: 2 },
  changeCol: { minWidth: 72, alignItems: 'flex-end' },
  change: { fontSize: 13, fontWeight: '700' },
  chevron: { color: colors.textDim, fontSize: 20, marginLeft: spacing.sm },
  empty: { alignItems: 'center', paddingTop: spacing.xl * 2, paddingHorizontal: spacing.xl },
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
  },
});
