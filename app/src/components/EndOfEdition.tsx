// Fin d'édition : récapitulatif du jour et « à demain ». Aucun contenu supplémentaire proposé.

import { StyleSheet, Text, View } from "react-native";

import { summarize } from "../lib/logic";
import { colors, serif, space } from "../lib/theme";
import type { EditionCard, ReadingState } from "../lib/types";

export function EndOfEdition({ cards, state }: { cards: EditionCard[]; state: ReadingState }) {
  const s = summarize(cards, state);
  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>That's all for today.</Text>
      <View style={styles.rows}>
        <Row n={s.read} label="read" />
        <Row n={s.skipped} label="skipped" />
        <Row n={s.saved} label="saved" />
      </View>
      <Text style={styles.bye}>See you tomorrow.</Text>
    </View>
  );
}

function Row({ n, label }: { n: number; label: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.n}>{n}</Text>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, justifyContent: "center", padding: space.xl, gap: space.xl },
  title: { ...serif, color: colors.text, fontSize: 28, lineHeight: 36 },
  rows: { gap: space.sm },
  row: { flexDirection: "row", alignItems: "baseline", gap: space.md },
  n: { ...serif, color: colors.text, fontSize: 24, minWidth: 32 },
  label: { color: colors.muted, fontSize: 15 },
  bye: { ...serif, color: colors.muted, fontSize: 18 },
});
