// Export d'un texte (Markdown, BibTeX) : menu de partage d'Android, ou téléchargement sur le web.

import { Platform } from "react-native";

/** Renvoie un message d'erreur, ou null si le partage a été proposé. */
export async function shareText(filename: string, text: string, mimeType: string): Promise<string | null> {
  try {
    if (Platform.OS === "web") {
      const url = URL.createObjectURL(new Blob([text], { type: mimeType }));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      return null;
    }
    const { File, Paths } = await import("expo-file-system");
    const Sharing = await import("expo-sharing");
    if (!(await Sharing.isAvailableAsync())) return "Sharing is not available on this device.";
    const file = new File(Paths.cache, filename);
    if (file.exists) file.delete();
    file.create();
    file.write(text);
    await Sharing.shareAsync(file.uri, { mimeType, dialogTitle: filename });
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}
