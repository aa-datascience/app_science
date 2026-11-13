import { Tabs } from "expo-router";

import { colors } from "../../lib/theme";

// V1 : Today et Settings. Notebook, Concepts et Stats viendront avec la V2.
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.background },
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.muted,
        tabBarIcon: () => null,
        tabBarIconStyle: { display: "none" },
        tabBarLabelStyle: { fontSize: 14, letterSpacing: 0.3 },
        tabBarLabelPosition: "beside-icon",
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Today" }} />
      <Tabs.Screen name="settings" options={{ title: "Settings" }} />
    </Tabs>
  );
}
