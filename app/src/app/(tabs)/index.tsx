// Accueil de l'édition : date, nombre d'articles, temps estimé, bouton Commencer.
// Si l'édition est finie, on arrive directement sur l'écran de fin.

import { router } from "expo-router";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { EndOfEdition } from "../../components/EndOfEdition";
import { Button } from "../../components/ui";
import { editionLabel } from "../../lib/logic";
import { useApp } from "../../lib/session";
import { colors, serif, space } from "../../lib/theme";

function formatDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
}

export default function Today() {
  const { cards, state, loading, fromCache, refresh } = useApp();

  if (loading && !cards.length) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator color={colors.muted} />
      </SafeAreaView>
    );
  }

  if (!cards.length) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.title}>No edition yet.</Text>
        <Text style={styles.muted}>
          {fromCache ? "You seem to be offline, and no edition is saved on this device." : "Today's edition is not ready."}
        </Text>
        <Button label="Check again" kind="quiet" onPress={refresh} style={{ marginTop: space.lg }} />
      </SafeAreaView>
    );
  }

  if (state.completed) {
    return (
      <SafeAreaView style={styles.wrap}>
        <EndOfEdition cards={cards} state={state} />
        <Pressable onPress={() => router.push("/edition")} style={styles.review}>
          <Text style={styles.muted}>Look back at today's papers</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const started = state.shown.length > 0;
  return (
    <SafeAreaView style={styles.wrap}>
      <View style={styles.home}>
        <Text style={styles.date}>{formatDate(cards[0].date)}</Text>
        <Text style={styles.title}>Today's edition</Text>
        <Text style={styles.meta}>{editionLabel(cards.length)}</Text>
        {fromCache && <Text style={styles.muted}>Offline: showing the edition saved on this device.</Text>}
        <Button label={started ? "Continue" : "Start"} onPress={() => router.push("/edition")} style={{ marginTop: space.xl }} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, backgroundColor: colors.background, justifyContent: "center", padding: space.xl, gap: space.sm },
  home: { flex: 1, justifyContent: "center", padding: space.xl, gap: space.sm, maxWidth: 520, width: "100%", alignSelf: "center" },
  date: { color: colors.muted, fontSize: 14, letterSpacing: 1, textTransform: "uppercase" },
  title: { ...serif, color: colors.text, fontSize: 34, lineHeight: 42 },
  meta: { ...serif, color: colors.text, fontSize: 18 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  review: { padding: space.lg, alignItems: "center" },
});
