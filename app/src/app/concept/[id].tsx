// Fiche d'un concept : définitions simple et experte, concepts liés, articles où il apparaît.
// Fusion d'un doublon dans cette fiche (décision 5 de la V2) : en ligne seulement.

import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, Label, MathText, Toggle } from "../../components/ui";
import { cachedConcepts, loadConcepts, mergeConcepts } from "../../lib/data";
import { conceptName, filterConcepts } from "../../lib/logic";
import { colors, serif, space } from "../../lib/theme";
import type { ConceptCard } from "../../lib/types";

export default function Concept() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [all, setAll] = useState<ConceptCard[] | null>(null);
  const [level, setLevel] = useState<"simple" | "expert">("simple");
  const [merging, setMerging] = useState(false);
  const [query, setQuery] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    setAll(await cachedConcepts()); // affichage immédiat, puis la base
    setAll((await loadConcepts()).concepts);
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  const concept = all?.find((c) => c.id === id);
  const others = useMemo(() => filterConcepts((all ?? []).filter((c) => c.id !== id), query), [all, id, query]);

  const merge = async (dup: ConceptCard) => {
    if (confirm !== dup.id) return setConfirm(dup.id);
    const error = await mergeConcepts(dup.id, id);
    setConfirm(null);
    if (error) return setMessage(`Merge failed: ${error}`);
    setMessage(`“${dup.name}” was merged into this concept.`);
    setMerging(false);
    setQuery("");
    await reload();
  };

  if (all && !concept) {
    return (
      <View style={styles.wrap}>
        <View style={styles.content}>
          <Text style={styles.muted}>This concept no longer exists: it may have been merged into another one.</Text>
        </View>
      </View>
    );
  }
  if (!concept) return <View style={styles.wrap} />;

  return (
    <ScrollView style={styles.wrap} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>{concept.name}</Text>

      <View style={styles.section}>
        <View style={styles.row}>
          <Toggle label="Simple" active={level === "simple"} onPress={() => setLevel("simple")} />
          <Toggle label="Expert" active={level === "expert"} onPress={() => setLevel("expert")} />
        </View>
        <MathText text={level === "simple" ? concept.simple_definition : concept.expert_definition} />
        <Text style={styles.muted}>Background definition written by the model; not checked against a paper.</Text>
      </View>

      {concept.related.length > 0 && (
        <View style={styles.section}>
          <Label>Related concepts</Label>
          <View style={styles.pills}>
            {concept.related.map((r) => (
              <Toggle key={r} label={conceptName(all ?? [], r)} active={false} onPress={() => router.push(`/concept/${r}`)} />
            ))}
          </View>
        </View>
      )}

      <View style={styles.section}>
        <Label>Papers</Label>
        {concept.papers.map((p) => (
          <Pressable
            key={p.paper_id}
            accessibilityRole="button"
            onPress={() => router.push({ pathname: "/paper/[id]", params: { id: p.paper_id, title: p.title } })}
            style={styles.paper}
          >
            <MathText text={p.title} size={16} />
            <Text style={styles.muted}>arXiv:{p.paper_id}</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.section}>
        {!merging ? (
          <Button label="Merge a duplicate into this concept" kind="quiet" onPress={() => setMerging(true)} />
        ) : (
          <>
            <Label>Merge a duplicate</Label>
            <Text style={styles.muted}>
              The concept you pick disappears; its papers and links move to “{concept.name}”. This cannot be undone.
            </Text>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search the duplicate"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
            />
            {others.slice(0, 20).map((c) => (
              <Pressable key={c.id} accessibilityRole="button" onPress={() => merge(c)} style={styles.paper}>
                <Text style={styles.name}>{confirm === c.id ? `Tap again to merge “${c.name}”` : c.name}</Text>
                <Text style={styles.muted} numberOfLines={1}>
                  {c.simple_definition}
                </Text>
              </Pressable>
            ))}
            <Toggle label="Cancel" active={false} onPress={() => { setMerging(false); setConfirm(null); }} />
          </>
        )}
        {message ? <Text style={styles.muted}>{message}</Text> : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, gap: space.lg, maxWidth: 680, width: "100%", alignSelf: "center", paddingBottom: space.xl * 2 },
  title: { ...serif, color: colors.text, fontSize: 26, lineHeight: 34 },
  section: { gap: space.sm, paddingTop: space.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  row: { flexDirection: "row", gap: space.xs },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  paper: { paddingVertical: space.sm, gap: 2 },
  name: { color: colors.text, fontSize: 16 },
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
});
