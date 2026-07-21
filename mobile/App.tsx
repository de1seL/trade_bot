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
import { Ionicons } from '@expo/vector-icons';
import {
  Currency,
  FuturesPosition,
  Holding,
  PricePair,
  Settings,
} from './src/types';
import { colors, spacing, radius } from './src/theme';
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
import { MarketScreen } from './src/screens/MarketScreen';
import { AddHoldingScreen } from './src/screens/AddHoldingScreen';
import { AddFuturesScreen } from './src/screens/AddFuturesScreen';
import { SettingsModal } from './src/screens/SettingsModal';

type Tab = 'portfolio' | 'futures' | 'market';

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
          {tab === 'portfolio' && (
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
          )}
          {tab === 'futures' && (
            <FuturesScreen
              summary={futuresSummary}
              refreshing={refreshing}
              priceError={priceError}
              onRefresh={() => refreshMarket(holdings, futures)}
              onAdd={() => setShowAddFutures(true)}
              onDelete={deleteFutures}
            />
          )}
          {tab === 'market' && <MarketScreen />}
        </View>

        {/* Alt sekme çubuğu */}
        <View style={styles.tabBar}>
          <TabButton
            icon="wallet-outline"
            iconActive="wallet"
            label="Portföy"
            active={tab === 'portfolio'}
            onPress={() => setTab('portfolio')}
          />
          <TabButton
            icon="flash-outline"
            iconActive="flash"
            label="Futures"
            active={tab === 'futures'}
            onPress={() => setTab('futures')}
          />
          <TabButton
            icon="trending-up-outline"
            iconActive="trending-up"
            label="Piyasa"
            active={tab === 'market'}
            onPress={() => setTab('market')}
          />
          <TabButton
            icon="settings-outline"
            iconActive="settings"
            label="Ayarlar"
            active={false}
            onPress={() => setShowSettings(true)}
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

type IoniconName = React.ComponentProps<typeof Ionicons>['name'];

function TabButton({
  icon,
  iconActive,
  label,
  active,
  onPress,
}: {
  icon: IoniconName;
  iconActive: IoniconName;
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.tabBtn} onPress={onPress} activeOpacity={0.7}>
      <View style={[styles.tabInner, active && styles.tabInnerActive]}>
        <Ionicons
          name={active ? iconActive : icon}
          size={22}
          color={active ? colors.primary : colors.textDim}
        />
        <Text style={[styles.tabText, active && styles.tabTextActive]}>
          {label}
        </Text>
      </View>
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
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
  },
  tabBtn: { flex: 1, alignItems: 'center' },
  tabInner: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    gap: 2,
  },
  tabInnerActive: { backgroundColor: colors.primary + '1F' },
  tabIcon: { fontSize: 19 },
  tabIconInactive: { opacity: 0.45 },
  tabText: { color: colors.textDim, fontSize: 11, fontWeight: '600' },
  tabTextActive: { color: colors.primary },
});
