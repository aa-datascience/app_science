// Réglages. V1 : le compte. Nombre d'articles, catégories et heures des notifications suivront.

import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, Label } from "../../components/ui";
import { useApp } from "../../lib/session";
import { supabase } from "../../lib/supabase";
import { colors, serif, space } from "../../lib/theme";

export default function Settings() {
  const { session } = useApp();
  return (
    <SafeAreaView style={styles.wrap}>
      <View style={styles.box}>
        <Text style={styles.title}>Settings</Text>
        <View>
          <Label>Account</Label>
          <Text style={styles.value}>{session?.user.email}</Text>
        </View>
        <Text style={styles.muted}>
          Papers per edition, followed categories and notification times will be adjustable here.
        </Text>
        <Button label="Sign out" kind="quiet" onPress={() => supabase.auth.signOut()} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  box: { padding: space.xl, gap: space.lg, maxWidth: 520, width: "100%", alignSelf: "center" },
  title: { ...serif, color: colors.text, fontSize: 28 },
  value: { color: colors.text, fontSize: 16 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
});
