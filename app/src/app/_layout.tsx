import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";

import { AppProvider, useApp } from "../lib/session";
import { colors } from "../lib/theme";

function Screens() {
  const { session, ready } = useApp();
  if (!ready) return <View style={{ flex: 1, backgroundColor: colors.background }} />;
  const signedIn = Boolean(session);
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
        headerShadowVisible: false,
        headerTitle: "",
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="edition" options={{ headerShown: false }} />
        <Stack.Screen name="paper/[id]" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AppProvider>
      <StatusBar style="light" />
      <Screens />
    </AppProvider>
  );
}
