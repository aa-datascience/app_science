// Statistiques de lecture : par semaine (montrés, lus, ignorés, taux de lecture, éditions terminées)
// et par sous-catégorie. Pas de compteur de jours consécutifs.

import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Label, Toggle } from "../../components/ui";
import { loadStats } from "../../lib/data";
import { percent, shortDate } from "../../lib/logic";
import { colors, serif, space } from "../../lib/theme";
import type { Stats as StatsData } from "../../lib/types";

const SPANS = [4, 8, 12];

export default function Stats() {
  const [weeks, setWeeks] = useState(4);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      loadStats(weeks).then((r) => {
        if (!alive) return;
        setStats(r.stats);
        setFromCache(r.fromCache);
        setLoaded(true);
      });
      return () => {
        alive = false;
      };
    }, [weeks]),
  );

  const rows = [...(stats?.weeks ?? [])].reverse(); // la semaine en cours d'abord
  const categories = stats?.categories ?? [];
  const most = Math.max(1, ...categories.map((c) => c.shown));

  return (
    <SafeAreaView style={styles.wrap}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Stats</Text>
        <View style={styles.spans}>
          {SPANS.map((n) => (
            <Toggle key={n} label={`${n} weeks`} active={weeks === n} onPress={() => setWeeks(n)} />
          ))}
        </View>
        {fromCache && loaded && <Text style={styles.muted}>Offline: showing the last figures saved on this device.</Text>}
        {loaded && !rows.length && <Text style={styles.muted}>Nothing to show yet: stats appear once you have read an edition.</Text>}

        {rows.length > 0 && (
          <View style={styles.section}>
            <Label>By week</Label>
            <View style={styles.tr}>
              <Text style={[styles.th, styles.week]}>Week of</Text>
              <Text style={styles.th}>Shown</Text>
              <Text style={styles.th}>Read</Text>
              <Text style={styles.th}>Skipped</Text>
              <Text style={styles.th}>Rate</Text>
              <Text style={styles.th}>Done</Text>
            </View>
            {rows.map((w) => (
              <View key={w.week} style={styles.tr}>
                <Text style={[styles.td, styles.week]}>{shortDate(w.week)}</Text>
                <Text style={styles.td}>{w.shown}</Text>
                <Text style={styles.td}>{w.read}</Text>
                <Text style={styles.td}>{w.skipped}</Text>
                <Text style={styles.td}>{percent(w.read_rate)}</Text>
                <Text style={styles.td}>{w.editions_completed}/7</Text>
              </View>
            ))}
            <Text style={styles.muted}>
              Read: you opened the explanation. Skipped: the card was shown and not opened. Done: editions finished that week.
            </Text>
          </View>
        )}

        {categories.length > 0 && (
          <View style={styles.section}>
            <Label>By subfield</Label>
            {categories.map((c) => (
              <View key={c.category} style={styles.cat}>
                <View style={styles.catHead}>
                  <Text style={styles.catName}>{c.category || "other"}</Text>
                  <Text style={styles.muted}>
                    {c.read} read of {c.shown} · {percent(c.read_rate)}
                  </Text>
                </View>
                <View style={[styles.bar, { width: `${(c.shown / most) * 100}%` }]}>
                  <View style={[styles.barRead, { width: `${c.shown ? (c.read / c.shown) * 100 : 0}%` }]} />
                </View>
              </View>
            ))}
            <Text style={styles.muted}>Bar length: papers shown. Light part: papers read.</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, paddingTop: space.xl, gap: space.md, maxWidth: 640, width: "100%", alignSelf: "center" },
  title: { ...serif, color: colors.text, fontSize: 28 },
  spans: { flexDirection: "row", gap: space.xs },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  section: { gap: space.sm, paddingTop: space.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  tr: { flexDirection: "row", paddingVertical: 6 },
  th: { flex: 1, color: colors.muted, fontSize: 12, textAlign: "right" },
  td: { flex: 1, color: colors.text, fontSize: 15, textAlign: "right", fontVariant: ["tabular-nums"] },
  week: { flex: 1.4, textAlign: "left" },
  cat: { gap: 5, paddingVertical: 5 },
  catHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", gap: space.sm },
  catName: { color: colors.text, fontSize: 15 },
  bar: { height: 6, minWidth: 6, backgroundColor: colors.border, borderRadius: 3, overflow: "hidden" },
  barRead: { height: 6, backgroundColor: colors.accent },
});
