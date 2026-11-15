// Fiche du carnet : l'article sauvegardé, sa note et ses tags. Le retirer annule le Save.

import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, Label, MathText } from "../../components/ui";
import { cachedNotebook, enqueue, patchCachedNotebook } from "../../lib/data";
import { parseTags } from "../../lib/logic";
import { useApp } from "../../lib/session";
import { colors, serif, space } from "../../lib/theme";
import type { NotebookEntry } from "../../lib/types";

export default function NotebookEntryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { unsave } = useApp();
  const [entry, setEntry] = useState<NotebookEntry | null>(null);
  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    cachedNotebook().then((all) => {
      const found = all.find((e) => e.paper_id === id) ?? null;
      setEntry(found);
      setNote(found?.note ?? "");
      setTags(found?.tags.join(", ") ?? "");
    });
  }, [id]);

  if (!entry) return <View style={styles.wrap} />;

  const parsed = parseTags(tags);
  const dirty = note !== entry.note || parsed.join(",") !== entry.tags.join(",");

  const save = async () => {
    const next = { ...entry, note, tags: parsed };
    setEntry(next);
    setTags(parsed.join(", "));
    await patchCachedNotebook((all) => all.map((e) => (e.paper_id === id ? next : e)));
    void enqueue({ kind: "notebook_update", paper_id: id, note, tags: parsed, at: new Date().toISOString() });
  };

  const remove = async () => {
    if (!confirming) return setConfirming(true);
    await patchCachedNotebook((all) => all.filter((e) => e.paper_id !== id));
    unsave(id);
    router.back();
  };

  return (
    <ScrollView style={styles.wrap} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {entry.plain_title ? <MathText text={entry.plain_title} size={24} style={{ lineHeight: 32 }} /> : null}
      <Text style={styles.original}>{entry.title}</Text>
      <Text style={styles.muted}>
        {entry.authors.join(", ")} · {entry.primary_category} · saved on {entry.saved_at.slice(0, 10)}
      </Text>
      {entry.finding ? <MathText text={entry.finding} size={16} /> : null}
      <Button label="Read the explanation" kind="quiet" onPress={() => router.push(`/paper/${id}`)} />

      <View style={styles.section}>
        <Label>Note</Label>
        <TextInput
          value={note}
          onChangeText={setNote}
          multiline
          placeholder="Your own words about this paper"
          placeholderTextColor={colors.muted}
          style={[styles.input, styles.note]}
          textAlignVertical="top"
        />
      </View>
      <View style={styles.section}>
        <Label>Tags</Label>
        <TextInput
          value={tags}
          onChangeText={setTags}
          placeholder="Separated by commas"
          placeholderTextColor={colors.muted}
          style={styles.input}
          autoCapitalize="none"
        />
      </View>
      <Button label={dirty ? "Save note and tags" : "Saved"} disabled={!dirty} onPress={save} />

      <View style={styles.section}>
        <Button label={confirming ? "Tap again to remove" : "Remove from notebook"} kind="quiet" onPress={remove} />
        <Text style={styles.muted}>Removing a paper also undoes its Save, and deletes its note and tags.</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, gap: space.md, maxWidth: 680, width: "100%", alignSelf: "center", paddingBottom: space.xl * 2 },
  original: { ...serif, color: colors.text, fontSize: 16, lineHeight: 23 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  section: { gap: space.xs, paddingTop: space.md },
  input: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 23,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 4,
    paddingHorizontal: space.md,
    paddingVertical: 12,
  },
  note: { minHeight: 140 },
});
