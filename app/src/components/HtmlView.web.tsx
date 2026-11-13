// Version navigateur de HtmlView : une iframe isolée, même page HTML que sur téléphone.

import { useEffect, useRef, useState } from "react";

export function HtmlView({ html }: { html: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(48);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source === ref.current?.contentWindow && typeof e.data?.mathHeight === "number") {
        setHeight(e.data.mathHeight);
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  return (
    <iframe
      ref={ref}
      srcDoc={html}
      sandbox="allow-scripts"
      title="content"
      style={{ border: 0, width: "100%", height, display: "block", background: "transparent" }}
    />
  );
}
