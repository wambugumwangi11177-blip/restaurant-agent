"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

export default function HelpPage() {
  const [text, setText] = useState("");
  useEffect(() => {
    api.get("/api/v1/eleven/help").then((r) => setText(r.data.pages));
  }, []);
  return (
    <OwnerShell title="Help">
      <pre className="whitespace-pre-wrap text-sm text-zinc-300">{text}</pre>
    </OwnerShell>
  );
}