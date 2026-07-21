import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  SafeAreaView,
  StyleSheet,
  Modal,
  StatusBar,
  View,
  Text,
  TouchableOpacity,
} from 'react-native';
import {
  Currency,
  FuturesPosition,
  Holding,
  PricePair,
  Settings,
} from './src/types';
import { colors, spacing } from './src/theme';
import {
  loadHoldings,
  saveHoldings,
  loadFutures,
  saveFutures,
  loadSettings,
  saveSettings,
  DEFAULT_SETTINGS,
} from './src/storage';
import { fetchMarket, CoinRef } from './src/prices';
import { buildSummary } from './src/utils/portfolio';
import { buildFuturesSummary } from './src/utils/futures';
import { PortfolioScreen } from './src/screens/PortfolioScreen';
import { FuturesScreen } from './src/screens/FuturesScreen';
import { AddHoldingScreen } from './src/screens/AddHoldingScreen';
import { AddFuturesScreen } from './src/screens/AddFuturesScreen';
import { SettingsModal } from './src/screens/SettingsModal';

type Tab = 'portfolio' | 'futures';

export default function App() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [futures, setFutures] = useState<FuturesPosition[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [pairs, setPairs] = useState<Record<string, PricePair>>({}); // coingeckoId -> {try,usd}
  const [usdTry, setUsdTry] = useState<number | null>(null);
  const [priceError, setPriceError] = useState<string | undefined>();
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>('portfolio');
  const [showAdd, setShowAdd] = useState(false);
  const [showAddFutures, setShowAddFutures] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const refreshMarket = useCallback(
    async (hList: Holding[], fList: FuturesPosition[]) => {
      setRefreshing(true);
      const refs: CoinRef[] = [];
      const seen = new Set<string>();
      const add = (coingeckoId?: string, symbol?: string) => {
        if (!coingeckoId || !symbol || seen.has(coingeckoId)) return;
        seen.add(coingeckoId);
        refs.push({ coingeckoId, symbol });
      };
      for (const h of hList) {
        if (h.type === 'crypto') add(h.coingeckoId, h.symbol);
      }
      for (const p of fList) add(p.coingeckoId, p.symbol);

      const res = await fetchMarket(refs);
      setPairs(res.pairs);
      if (res.usdTry !== null) setUsdTry(res.usdTry);
      setPriceError(res.ok ? undefined : res.error);
      setRefreshing(false);
    },
    []
  );

  // Açılışta kayıtlı veriyi yükle, sonra fiyatları çek.
  useEffect(() => {
    (async () => {
      const [h, f, s] = await Promise.all([
        loadHoldings(),
        loadFutures(),
        loadSettings(),
      ]);
      setHoldings(h);
      setFutures(f);
      setSettings(s);
      refreshMarket(h, f);
    })();
  }, [refreshMarket]);

  // Spot fiyat haritası: holding.id -> {try,usd}
  const spotPriceMap = useMemo(() => {
    const m: Record<string, PricePair> = {};
    for (const h of holdings) {
      if (h.type === 'crypto' && h.coingeckoId && pairs[h.coingeckoId]) {
        m[h.id] = pairs[h.coingeckoId];
      }
    }
    return m;
  }, [holdings, pairs]);

  const summary = useMemo(
    () =>
      buildSummary(
        holdings,
        spotPriceMap,
        usdTry,
        settings,
        settings.displayCurrency
      ),
    [holdings, spotPriceMap, usdTry, settings]
  );

  const futuresSummary = useMemo(
    () => buildFuturesSummary(futures, pairs),
    [futures, pairs]
  );

  const addHolding = useCallback(
    (h: Holding) => {
      const next = [...holdings, h];
      setHoldings(next);
      saveHoldings(next);
      setShowAdd(false);
      refreshMarket(next, futures);
    },
    [holdings, futures, refreshMarket]
  );

  const deleteHolding = useCallback(
    (id: string) => {
      const next = holdings.filter((h) => h.id !== id);
      setHoldings(next);
      saveHoldings(next);
    },
    [holdings]
  );

  const addFutures = useCallback(
    (p: FuturesPosition) => {
      const next = [...futures, p];
      setFutures(next);
      saveFutures(next);
      setShowAddFutures(false);
      refreshMarket(holdings, next);
    },
    [holdings, futures, refreshMarket]
  );

  const deleteFutures = useCallback(
    (id: string) => {
      const next = futures.filter((p) => p.id !== id);
      setFutures(next);
      saveFutures(next);
    },
    [futures]
  );

  const updateSettings = useCallback((s: Settings) => {
    setSettings(s);
    saveSettings(s);
    setShowSettings(false);
  }, []);

  const setCurrency = useCallback(
    (c: Currency) => {
      const s = { ...settings, displayCurrency: c };
      setSettings(s);
      saveSettings(s);
    },
    [settings]
  );

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />
      <SafeAreaView style={styles.root}>
        <View style={styles.screen}>
          {tab === 'portfolio' ? (
            <PortfolioScreen
              summary={summary}
              displayCurrency={settings.displayCurrency}
              refreshing={refreshing}
              priceError={priceError}
              onSetCurrency={setCurrency}
              onRefresh={() => refreshMarket(holdings, futures)}
              onAdd={() => setShowAdd(true)}
              onDelete={deleteHolding}
              onOpenSettings={() => setShowSettings(true)}
            />
          ) : (
            <FuturesScreen
              summary={futuresSummary}
              refreshing={refreshing}
              priceError={priceError}
              onRefresh={() => refreshMarket(holdings, futures)}
              onAdd={() => setShowAddFutures(true)}
              onDelete={deleteFutures}
            />
          )}
        </View>

        {/* Alt sekme çubuğu */}
        <View style={styles.tabBar}>
          <TabButton
            label="Portföy"
            active={tab === 'portfolio'}
            onPress={() => setTab('portfolio')}
          />
          <TabButton
            label="Futures"
            active={tab === 'futures'}
            onPress={() => setTab('futures')}
          />
        </View>
      </SafeAreaView>

      <Modal visible={showAdd} animationType="slide" presentationStyle="pageSheet">
        <AddHoldingScreen
          currentUsdTry={usdTry}
          onAdd={addHolding}
          onClose={() => setShowAdd(false)}
        />
      </Modal>

      <Modal
        visible={showAddFutures}
        animationType="slide"
        presentationStyle="pageSheet"
      >
        <AddFuturesScreen onAdd={addFutures} onClose={() => setShowAddFutures(false)} />
      </Modal>

      <Modal
        visible={showSettings}
        animationType="slide"
        presentationStyle="pageSheet"
      >
        <SettingsModal
          settings={settings}
          onSave={updateSettings}
          onClose={() => setShowSettings(false)}
        />
      </Modal>
    </View>
  );
}

function TabButton({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.tabBtn} onPress={onPress} activeOpacity={0.7}>
      <Text style={[styles.tabText, active && styles.tabTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1 },
  tabBar: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.card,
  },
  tabBtn: { flex: 1, alignItems: 'center', paddingVertical: spacing.md },
  tabText: { color: colors.textDim, fontSize: 14, fontWeight: '600' },
  tabTextActive: { color: colors.primary },
});
