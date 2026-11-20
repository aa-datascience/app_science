// Fin d'édition : récapitulatif du jour et « à demain ». Aucun contenu supplémentaire proposé.

import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { countNewConcepts } from "../lib/data";
import { summarize } from "../lib/logic";
import { colors, serif, space } from "../lib/theme";
import type { EditionCard, ReadingState } from "../lib/types";

export function EndOfEdition({ cards, state }: { cards: EditionCard[]; state: ReadingState }) {
  const s = summarize(cards, state);
  // Concepts créés par les articles de cette édition ; rien n'est affiché hors ligne.
  const [concepts, setConcepts] = useState<number | null>(null);
  const ids = cards.map((c) => c.arxiv_id).join(",");
  useEffect(() => {
    let alive = true;
    countNewConcepts(ids ? ids.split(",") : []).then((n) => alive && setConcepts(n));
    return () => {
      alive = false;
    };
  }, [ids]);
  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>That's all for today.</Text>
      <View style={styles.rows}>
        <Row n={s.read} label="read" />
        <Row n={s.skipped} label="skipped" />
        <Row n={s.saved} label="saved" />
        {concepts !== null && concepts > 0 && <Row n={concepts} label={concepts === 1 ? "new concept" : "new concepts"} />}
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
