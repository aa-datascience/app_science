// Concepts : les concepts prérequis rencontrés dans les articles ouverts, avec recherche.
// Une fiche s'ouvre d'un appui (définitions, concepts liés, articles où il apparaît).

import { router, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { loadConcepts } from "../../lib/data";
import { filterConcepts } from "../../lib/logic";
import { colors, serif, space } from "../../lib/theme";
import type { ConceptCard } from "../../lib/types";

export default function Concepts() {
  const [concepts, setConcepts] = useState<ConceptCard[] | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [query, setQuery] = useState("");

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      loadConcepts().then((r) => {
        if (!alive) return;
        setConcepts(r.concepts);
        setFromCache(r.fromCache);
      });
      return () => {
        alive = false;
      };
    }, []),
  );

  const visible = useMemo(() => filterConcepts(concepts ?? [], query), [concepts, query]);

  return (
    <SafeAreaView style={styles.wrap}>
      <FlatList
        data={visible}
        keyExtractor={(c) => c.id}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.title}>Concepts</Text>
            {fromCache && concepts !== null && <Text style={styles.muted}>Offline: showing the concepts saved on this device.</Text>}
            {concepts && concepts.length > 0 && (
              <>
                <TextInput
                  value={query}
                  onChangeText={setQuery}
                  placeholder="Search concepts"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <Text style={styles.muted}>
                  {visible.length} of {concepts.length} concept{concepts.length > 1 ? "s" : ""}
                </Text>
              </>
            )}
            {concepts && concepts.length === 0 && (
              <Text style={styles.muted}>
                No concepts yet. Each paper you open adds the one to three concepts it builds on.
              </Text>
            )}
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/concept/${item.id}`)} accessibilityRole="button" style={styles.row}>
            <Text style={styles.rowTitle}>{item.name}</Text>
            <Text style={styles.def} numberOfLines={2}>
              {item.simple_definition}
            </Text>
            <Text style={styles.muted}>
              {item.paper_count} paper{Number(item.paper_count) === 1 ? "" : "s"}
            </Text>
          </Pressable>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, paddingTop: space.xl, maxWidth: 640, width: "100%", alignSelf: "center" },
  header: { gap: space.md, marginBottom: space.md },
  title: { ...serif, color: colors.text, fontSize: 28 },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  input: {
    color: colors.text,
    fontSize: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 4,
    paddingHorizontal: space.md,
    paddingVertical: 12,
  },
  row: { paddingVertical: space.md, gap: 4, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rowTitle: { ...serif, color: colors.text, fontSize: 18, lineHeight: 25 },
  def: { color: colors.text, fontSize: 14, lineHeight: 20 },
});
