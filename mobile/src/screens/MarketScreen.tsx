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

type Category = 'crypto' | 'stock' | 'gold' | 'silver';

const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'crypto', label: 'Kripto' },
  { key: 'stock', label: 'Hisse' },
  { key: 'gold', label: 'Altın' },
  { key: 'silver', label: 'Gümüş' },
];

export function MarketScreen() {
  const [category, setCategory] = useState<Category>('crypto');
  const [quotes, setQuotes] = useState<MarketQuote[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Kripto araması
  const [query, setQuery] = useState('');
  const [searchQuotes, setSearchQuotes] = useState<MarketQuote[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  const load = useCallback(async (cat: Category) => {
    if (cat === 'stock' || cat === 'silver') {
      setQuotes([]);
      setError('');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data =
        cat === 'crypto' ? await fetchCryptoMarket() : await fetchGoldMarket();
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

  // Arama (yalnızca kripto): yaz → CoinGecko'da bul → fiyatlarını getir.
  useEffect(() => {
    if (category !== 'crypto') return;
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
        const coins = await searchCoins(q);
        const top = coins.slice(0, 12);
        const data = await fetchQuotesForCoins(top);
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

  const comingSoon = category === 'stock' || category === 'silver';
  const searching = category === 'crypto' && query.trim().length >= 2;
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

      {/* Kripto arama kutusu */}
      {category === 'crypto' && (
        <View style={styles.searchWrap}>
          <TextInput
            style={styles.search}
            placeholder="Coin ara (pepe, render, sui…)"
            placeholderTextColor={colors.textDim}
            value={query}
            onChangeText={setQuery}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {searchLoading && (
            <ActivityIndicator color={colors.textDim} style={styles.searchSpin} />
          )}
        </View>
      )}

      {comingSoon ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>
            {category === 'stock' ? 'Hisse' : 'Gümüş'} verisi yakında
          </Text>
          <Text style={styles.emptyText}>
            Bu kategori için canlı fiyat kaynağı henüz bağlanmadı. Kripto ve
            altın şu an canlı; hisse (BIST) ve gümüş bir sonraki adımda
            eklenecek — arama da o zaman burada çalışacak.
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
          renderItem={({ item }) => <QuoteRow item={item} />}
        />
      )}
    </View>
  );
}

function QuoteRow({ item }: { item: MarketQuote }) {
  const up = item.changePct >= 0;
  const color = up ? colors.green : colors.red;
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={styles.symbol}>{item.symbol}</Text>
        <Text style={styles.name} numberOfLines={1}>
          {item.name}
        </Text>
      </View>
      <View style={styles.rightCol}>
        <Text style={styles.priceTry}>{formatTRY(item.priceTry)}</Text>
        <Text style={styles.priceUsd}>{formatUSD(item.priceUsd)}</Text>
      </View>
      <View style={styles.changeCol}>
        <Text style={[styles.change, { color }]}>{formatPct(item.changePct)}</Text>
      </View>
    </View>
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
