// Affiche une page HTML qui annonce sa propre hauteur (voir buildMathHtml). Version téléphone : WebView.

import { useState } from "react";
import { WebView } from "react-native-webview";

export function HtmlView({ html }: { html: string }) {
  const [height, setHeight] = useState(48);
  return (
    <WebView
      originWhitelist={["*"]}
      source={{ html }}
      style={{ height, backgroundColor: "transparent" }}
      scrollEnabled={false}
      showsVerticalScrollIndicator={false}
      onMessage={(e) => {
        const h = Number(e.nativeEvent.data);
        if (h > 0) setHeight(h);
      }}
    />
  );
}
