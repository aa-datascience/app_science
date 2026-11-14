// Réglages. V1 : le compte et les notifications. Le profil et les autres réglages viendront avec la V2.

import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, Label } from "../../components/ui";
import { type PushState, registerPush } from "../../lib/notifications";
import { useApp } from "../../lib/session";
import { supabase } from "../../lib/supabase";
import { colors, serif, space } from "../../lib/theme";

function describe(push: PushState | null): string {
  if (!push) return "Checking…";
  if (push.state === "enabled") return "On. One in the morning when the edition is ready, one reminder in the evening if it is unfinished. Nothing else.";
  if (push.state === "denied") return "Off: notifications are not allowed for this app. Allow them in Android settings, then tap the button below.";
  if (push.state === "unsupported") return push.reason;
  return `Could not register this phone: ${push.message}`;
}

export default function Settings() {
  const { session } = useApp();
  const [push, setPush] = useState<PushState | null>(null);

  useEffect(() => {
    registerPush(false).then(setPush);
  }, []);

  return (
    <SafeAreaView style={styles.wrap}>
      <View style={styles.box}>
        <Text style={styles.title}>Settings</Text>
        <View>
          <Label>Account</Label>
          <Text style={styles.value}>{session?.user.email}</Text>
        </View>
        <View style={{ gap: space.sm }}>
          <Label>Notifications</Label>
          <Text style={styles.muted}>{describe(push)}</Text>
          {push && push.state !== "enabled" && push.state !== "unsupported" && (
            <Button label="Turn on notifications" kind="quiet" onPress={() => registerPush(true).then(setPush)} />
          )}
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
