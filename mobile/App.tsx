import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SafeAreaView, StyleSheet, Modal, StatusBar, View } from 'react-native';
import { Holding, Settings } from './src/types';
import { colors } from './src/theme';
import {
  loadHoldings,
  saveHoldings,
  loadSettings,
  saveSettings,
  DEFAULT_SETTINGS,
} from './src/storage';
import { fetchPrices } from './src/prices';
import { buildSummary } from './src/utils/portfolio';
import { PortfolioScreen } from './src/screens/PortfolioScreen';
import { AddHoldingScreen } from './src/screens/AddHoldingScreen';
import { SettingsModal } from './src/screens/SettingsModal';

export default function App() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [priceMap, setPriceMap] = useState<Record<string, number>>({});
  const [priceError, setPriceError] = useState<string | undefined>();
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const refreshPrices = useCallback(async (list: Holding[]) => {
    setRefreshing(true);
    const res = await fetchPrices(list);
    setPriceMap(res.priceMap);
    setPriceError(res.ok ? undefined : res.error);
    setRefreshing(false);
  }, []);

  // Açılışta kayıtlı veriyi yükle, sonra fiyatları çek.
  useEffect(() => {
    (async () => {
      const [h, s] = await Promise.all([loadHoldings(), loadSettings()]);
      setHoldings(h);
      setSettings(s);
      refreshPrices(h);
    })();
  }, [refreshPrices]);

  const summary = useMemo(
    () => buildSummary(holdings, priceMap, settings),
    [holdings, priceMap, settings]
  );

  const addHolding = useCallback(
    (h: Holding) => {
      const next = [...holdings, h];
      setHoldings(next);
      saveHoldings(next);
      setShowAdd(false);
      refreshPrices(next);
    },
    [holdings, refreshPrices]
  );

  const deleteHolding = useCallback(
    (id: string) => {
      const next = holdings.filter((h) => h.id !== id);
      setHoldings(next);
      saveHoldings(next);
    },
    [holdings]
  );

  const updateSettings = useCallback((s: Settings) => {
    setSettings(s);
    saveSettings(s);
    setShowSettings(false);
  }, []);

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />
      <SafeAreaView style={styles.root}>
        <PortfolioScreen
          summary={summary}
          refreshing={refreshing}
          priceError={priceError}
          onRefresh={() => refreshPrices(holdings)}
          onAdd={() => setShowAdd(true)}
          onDelete={deleteHolding}
          onOpenSettings={() => setShowSettings(true)}
        />
      </SafeAreaView>

      <Modal visible={showAdd} animationType="slide" presentationStyle="pageSheet">
        <AddHoldingScreen onAdd={addHolding} onClose={() => setShowAdd(false)} />
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

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
});
