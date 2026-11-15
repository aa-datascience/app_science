// Profil : ce que le pipeline a appris (poids par catégorie et par mot-clé, niveaux par sous-domaine),
// visible et modifiable à la main, avec la raison du dernier changement. Et les réglages de l'édition :
// nombre d'articles, heures des notifications, catégories suivies.

import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, Label, Toggle } from "../components/ui";
import { ARXIV_CATEGORIES } from "../lib/categories";
import { loadProfile, saveProfile } from "../lib/data";
import {
  DEFAULT_SETTINGS,
  describeChange,
  lastChanges,
  profileDiff,
  shiftTime,
  SIZE_MAX,
  SIZE_MIN,
  stepWeight,
  weightId,
} from "../lib/logic";
import { colors, serif, space } from "../lib/theme";
import type { AppSettings, Level, LevelName, ProfileData, Weight } from "../lib/types";

type Draft = { settings: AppSettings; weights: Weight[]; levels: Level[] };
const LEVELS: LevelName[] = ["beginner", "intermediate", "expert"];

export default function Profile() {
  const [data, setData] = useState<ProfileData | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const r = await loadProfile();
    setData(r.profile);
    setDraft(r.profile && { settings: r.profile.settings, weights: r.profile.weights, levels: r.profile.levels });
    setFromCache(r.fromCache);
    setLoaded(true);
  };
  useEffect(() => {
    void load();
  }, []);

  if (!loaded) return <View style={styles.wrap} />;
  if (!data || !draft) {
    return (
      <View style={[styles.wrap, styles.content]}>
        <Text style={styles.title}>Profile</Text>
        <Text style={styles.muted}>The profile could not be loaded. You seem to be offline.</Text>
        <Button label="Try again" kind="quiet" onPress={load} />
      </View>
    );
  }

  const settings = { ...DEFAULT_SETTINGS, ...draft.settings };
  const last = lastChanges(data.changes);
  const diff = profileDiff(data, draft);
  const dirty =
    JSON.stringify(data.settings) !== JSON.stringify(draft.settings) ||
    diff.weights.length + diff.removed.length + diff.levels.length > 0;

  const setSetting = (patch: AppSettings) => setDraft({ ...draft, settings: { ...draft.settings, ...patch } });
  const setWeight = (w: Weight, patch: Partial<Weight>) =>
    setDraft({ ...draft, weights: draft.weights.map((x) => (weightId(x) === weightId(w) ? { ...x, ...patch } : x)) });
  const removeWeight = (w: Weight) => setDraft({ ...draft, weights: draft.weights.filter((x) => weightId(x) !== weightId(w)) });
  const addCategory = (key: string) => {
    const weight: Weight = { kind: "category", key, weight: 1, baseline: 1, locked: false };
    setDraft({ ...draft, weights: [...draft.weights, weight].sort((a, b) => a.key.localeCompare(b.key)) });
  };
  const levelOf = (category: string): Level =>
    draft.levels.find((l) => l.category === category) ?? { category, level: "intermediate", drift: 0, locked: false };
  const setLevel = (category: string, patch: Partial<Level>) => {
    const next = { ...levelOf(category), ...patch };
    setDraft({ ...draft, levels: [...draft.levels.filter((l) => l.category !== category), next] });
  };

  const save = async () => {
    setSaving(true);
    const message = await saveProfile(data, draft);
    setError(message ? `Could not save (are you offline?): ${message}` : "");
    if (!message) await load();
    setSaving(false);
  };

  const categories = draft.weights.filter((w) => w.kind === "category");
  const keywords = draft.weights.filter((w) => w.kind === "keyword" && w.weight > 0);
  const negatives = draft.weights.filter((w) => w.kind === "keyword" && w.weight < 0);
  const followed = new Set(categories.map((w) => w.key));
  const levelCategories = [...new Set([...followed, ...draft.levels.map((l) => l.category)])].sort();

  const weightRow = (w: Weight, opts: { lock: boolean; remove: boolean }) => (
    <View key={weightId(w)} style={styles.row}>
      <View style={styles.rowHead}>
        <Text style={styles.name}>{w.key}</Text>
        <Stepper
          value={Math.abs(w.weight).toFixed(Math.abs(w.weight * 10 - Math.round(w.weight * 10)) < 1e-6 ? 1 : 2)}
          onMinus={() => setWeight(w, { weight: stepWeight(w.weight, -1) })}
          onPlus={() => setWeight(w, { weight: stepWeight(w.weight, 1) })}
        />
      </View>
      <View style={styles.rowFoot}>
        <Text style={[styles.small, { flex: 1 }]}>{describeChange(last[weightId(w)]) || "No change yet"}</Text>
        {opts.lock && <Link label={w.locked ? "Locked" : "Lock"} active={w.locked} onPress={() => setWeight(w, { locked: !w.locked })} />}
        {opts.remove && <Link label="Remove" onPress={() => removeWeight(w)} />}
      </View>
    </View>
  );

  return (
    <View style={styles.wrap}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Profile</Text>
        {fromCache && <Text style={styles.muted}>Offline: showing the profile saved on this device. Changes cannot be saved.</Text>}

        <View style={styles.section}>
          <Label>Edition</Label>
          <View style={styles.rowHead}>
            <Text style={styles.name}>Papers per edition</Text>
            <Stepper
              value={String(settings.edition_size)}
              onMinus={() => setSetting({ edition_size: Math.max(SIZE_MIN, settings.edition_size - 1) })}
              onPlus={() => setSetting({ edition_size: Math.min(SIZE_MAX, settings.edition_size + 1) })}
            />
          </View>
          <Text style={styles.small}>Applies from the next edition. The monthly budget can still make an edition shorter.</Text>
        </View>

        <View style={styles.section}>
          <Label>Notifications</Label>
          <View style={styles.rowHead}>
            <Text style={styles.name}>Morning, edition ready</Text>
            <Stepper
              value={settings.morning_time}
              onMinus={() => setSetting({ morning_time: shiftTime(settings.morning_time, -30, "06:00", "10:00") })}
              onPlus={() => setSetting({ morning_time: shiftTime(settings.morning_time, 30, "06:00", "10:00") })}
            />
          </View>
          <View style={styles.rowHead}>
            <Text style={styles.name}>Evening reminder</Text>
            <Stepper
              value={settings.evening_time}
              onMinus={() => setSetting({ evening_time: shiftTime(settings.evening_time, -30, "17:00", "22:00") })}
              onPlus={() => setSetting({ evening_time: shiftTime(settings.evening_time, 30, "17:00", "22:00") })}
            />
          </View>
          <Text style={styles.small}>Sent at the first hourly check after this time, so up to an hour later.</Text>
        </View>

        {!data.weights.length && (
          <View style={styles.section}>
            <Label>What the app has learned</Label>
            <Text style={styles.muted}>Your weights appear here after the next nightly edition is built.</Text>
          </View>
        )}

        {data.weights.length > 0 && (
          <>
            <View style={styles.section}>
              <Label>Followed categories</Label>
              <Text style={styles.small}>
                Weights move with your feedback (0.2 to 2.0) and drift back to the value you set. A locked weight never moves.
              </Text>
              {categories.map((w) => weightRow(w, { lock: true, remove: true }))}
              <Button label={adding ? "Close the list" : "Follow another category"} kind="quiet" onPress={() => setAdding(!adding)} />
              {adding && (
                <View style={styles.chips}>
                  {ARXIV_CATEGORIES.filter((c) => !followed.has(c)).map((c) => (
                    <Toggle key={c} label={c} active={false} onPress={() => addCategory(c)} />
                  ))}
                </View>
              )}
            </View>

            <View style={styles.section}>
              <Label>Keywords</Label>
              {keywords.map((w) => weightRow(w, { lock: true, remove: false }))}
            </View>

            {negatives.length > 0 && (
              <View style={styles.section}>
                <Label>Down-weighted keywords</Label>
                <Text style={styles.small}>Papers with these words rank lower. These are never changed by feedback.</Text>
                {negatives.map((w) => weightRow(w, { lock: false, remove: false }))}
              </View>
            )}

            <View style={styles.section}>
              <Label>Your level by subfield</Label>
              <Text style={styles.small}>
                Explanations are written for this level. Three more “too easy” than “too hard” raise it, and the reverse lowers it.
              </Text>
              {levelCategories.map((c) => {
                const l = levelOf(c);
                return (
                  <View key={c} style={styles.row}>
                    <Text style={styles.name}>{c}</Text>
                    <View style={styles.levels}>
                      {LEVELS.map((name) => (
                        <Toggle key={name} label={name} active={l.level === name} onPress={() => setLevel(c, { level: name })} />
                      ))}
                    </View>
                    <View style={styles.rowFoot}>
                      <Text style={[styles.small, { flex: 1 }]}>{describeChange(last[`level:${c}`]) || "No change yet"}</Text>
                      <Link label={l.locked ? "Locked" : "Lock"} active={l.locked} onPress={() => setLevel(c, { locked: !l.locked })} />
                    </View>
                  </View>
                );
              })}
            </View>
          </>
        )}
      </ScrollView>

      {(dirty || Boolean(error)) && (
        <View style={styles.bar}>
          {error ? <Text style={styles.small}>{error}</Text> : null}
          <View style={styles.barButtons}>
            <Button label="Discard" kind="quiet" onPress={() => { setDraft({ settings: data.settings, weights: data.weights, levels: data.levels }); setError(""); }} style={{ flex: 1 }} />
            <Button label={saving ? "Saving…" : "Save changes"} disabled={saving || !dirty} onPress={save} style={{ flex: 1 }} />
          </View>
        </View>
      )}
    </View>
  );
}

function Stepper({ value, onMinus, onPlus }: { value: string; onMinus: () => void; onPlus: () => void }) {
  return (
    <View style={styles.stepper}>
      <Pressable onPress={onMinus} hitSlop={8} accessibilityRole="button" accessibilityLabel="Less" style={styles.step}>
        <Text style={styles.stepLabel}>−</Text>
      </Pressable>
      <Text style={styles.value}>{value}</Text>
      <Pressable onPress={onPlus} hitSlop={8} accessibilityRole="button" accessibilityLabel="More" style={styles.step}>
        <Text style={styles.stepLabel}>+</Text>
      </Pressable>
    </View>
  );
}

function Link({ label, active, onPress }: { label: string; active?: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={10} accessibilityRole="button" accessibilityState={{ selected: Boolean(active) }}>
      <Text style={[styles.link, active && { color: colors.accent }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, gap: space.md, maxWidth: 640, width: "100%", alignSelf: "center", paddingBottom: space.xl * 2 },
  title: { ...serif, color: colors.text, fontSize: 28 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  small: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  section: { gap: space.sm, paddingTop: space.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  row: { gap: 6, paddingVertical: space.sm },
  rowHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.sm },
  rowFoot: { flexDirection: "row", alignItems: "flex-start", gap: space.md },
  name: { color: colors.text, fontSize: 16, flexShrink: 1 },
  stepper: { flexDirection: "row", alignItems: "center", gap: space.sm },
  step: {
    width: 36,
    height: 36,
    borderRadius: 4,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  stepLabel: { color: colors.text, fontSize: 20, lineHeight: 24 },
  value: { color: colors.text, fontSize: 16, minWidth: 48, textAlign: "center", fontVariant: ["tabular-nums"] },
  link: { color: colors.muted, fontSize: 13, textDecorationLine: "underline" },
  levels: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  bar: {
    padding: space.md,
    gap: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
  barButtons: { flexDirection: "row", gap: space.sm, maxWidth: 640, width: "100%", alignSelf: "center" },
});
