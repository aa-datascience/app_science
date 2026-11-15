// Carnet : les articles sauvegardés, avec recherche, filtre par tag et export (Markdown, BibTeX).

import { router, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, Toggle } from "../../components/ui";
import { loadNotebook } from "../../lib/data";
import { allTags, filterNotebook, toBibtex, toMarkdown } from "../../lib/logic";
import { shareText } from "../../lib/share";
import { colors, serif, space } from "../../lib/theme";
import type { NotebookEntry } from "../../lib/types";

export default function Notebook() {
  const [entries, setEntries] = useState<NotebookEntry[] | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      loadNotebook().then((r) => {
        if (!alive) return;
        setEntries(r.entries);
        setFromCache(r.fromCache);
      });
      return () => {
        alive = false;
      };
    }, []),
  );

  const tags = useMemo(() => allTags(entries ?? []), [entries]);
  const activeTag = tag && tags.includes(tag) ? tag : null;
  const visible = useMemo(() => filterNotebook(entries ?? [], query, activeTag), [entries, query, activeTag]);

  const exportAs = async (kind: "md" | "bib") => {
    const text = kind === "md" ? toMarkdown(visible) : toBibtex(visible);
    const error = await shareText(kind === "md" ? "notebook.md" : "notebook.bib", text, kind === "md" ? "text/markdown" : "text/plain");
    setMessage(error ? `Export failed: ${error}` : "");
  };

  return (
    <SafeAreaView style={styles.wrap}>
      <FlatList
        data={visible}
        keyExtractor={(e) => e.paper_id}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.title}>Notebook</Text>
            {fromCache && <Text style={styles.muted}>Offline: showing the notebook saved on this device.</Text>}
            {entries && entries.length > 0 && (
              <>
                <TextInput
                  value={query}
                  onChangeText={setQuery}
                  placeholder="Search titles, notes, authors"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                {tags.length > 0 && (
                  <View style={styles.tags}>
                    {tags.map((t) => (
                      <Toggle key={t} label={t} active={activeTag === t} onPress={() => setTag(activeTag === t ? null : t)} />
                    ))}
                  </View>
                )}
                <Text style={styles.muted}>
                  {visible.length} of {entries.length} paper{entries.length > 1 ? "s" : ""}
                </Text>
              </>
            )}
            {entries && entries.length === 0 && (
              <Text style={styles.muted}>Nothing saved yet. Tap Save on a card to keep a paper here.</Text>
            )}
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/notebook/${item.paper_id}`)} accessibilityRole="button" style={styles.row}>
            <Text style={styles.rowTitle}>{item.plain_title || item.title}</Text>
            <Text style={styles.muted} numberOfLines={1}>
              {item.authors.slice(0, 3).join(", ")}
              {item.authors.length > 3 ? " et al." : ""} · {item.saved_at.slice(0, 10)}
            </Text>
            {item.note.trim() ? (
              <Text style={styles.note} numberOfLines={2}>
                {item.note.trim()}
              </Text>
            ) : null}
            {item.tags.length > 0 && <Text style={styles.rowTags}>{item.tags.join(" · ")}</Text>}
          </Pressable>
        )}
        ListFooterComponent={
          visible.length > 0 ? (
            <View style={styles.footer}>
              <Text style={styles.muted}>Export the {visible.length === entries?.length ? "notebook" : "papers listed above"}</Text>
              <View style={styles.exports}>
                <Button label="Markdown" kind="quiet" onPress={() => exportAs("md")} style={{ flex: 1 }} />
                <Button label="BibTeX" kind="quiet" onPress={() => exportAs("bib")} style={{ flex: 1 }} />
              </View>
              {message ? <Text style={styles.muted}>{message}</Text> : null}
            </View>
          ) : undefined
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, paddingTop: space.xl, maxWidth: 640, width: "100%", alignSelf: "center" },
  header: { gap: space.md, marginBottom: space.md },
  title: { ...serif, color: colors.text, fontSize: 28 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  input: {
    color: colors.text,
    fontSize: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 4,
    paddingHorizontal: space.md,
    paddingVertical: 12,
  },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  row: { paddingVertical: space.md, gap: 4, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rowTitle: { ...serif, color: colors.text, fontSize: 18, lineHeight: 25 },
  note: { color: colors.text, fontSize: 14, lineHeight: 20, marginTop: 2 },
  rowTags: { color: colors.accent, fontSize: 12, letterSpacing: 0.5, marginTop: 2 },
  footer: { gap: space.sm, paddingTop: space.lg, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  exports: { flexDirection: "row", gap: space.sm },
});
