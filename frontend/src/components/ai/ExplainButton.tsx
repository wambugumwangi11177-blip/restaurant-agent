"use client";

/**
 * frontend/src/components/ai/ExplainButton.tsx
 * ──────────────────────────────────────────────
 * On-demand "Explain this to me": sends one insight to the grounded reasoning
 * layer (POST /ai/explain) and shows a plain-language paragraph. Degrades
 * quietly when no LLM provider is configured (available:false → a short notice).
 */

import { useState } from "react";
import { Info } from "lucide-react";
import api from "@/lib/api";

export function ExplainButton({ item, label }: { item: Record<string, any>; label?: string }) {
    const [state, setState] = useState<"idle" | "loading" | "done" | "none">("idle");
    const [text, setText] = useState("");

    const explain = async () => {
        if (state === "loading") return;
        setState("loading");
        try {
            const res = await api.post("/ai/explain", { item, label });
            if (res.data?.available && res.data.explanation) {
                const n = res.data.explanation;
                const extra = (n.actions || []).slice(0, 1).map((a: any) => a.action).join(" ");
                setText([n.headline, extra].filter(Boolean).join(" — "));
                setState("done");
            } else {
                setState("none");
            }
        } catch {
            setState("none");
        }
    };

    if (state === "done") {
        return <p className="text-[11px] text-[#a3a3a3] mt-1 leading-relaxed bg-[#0a0a0a] border border-[#1a1a1a] rounded-md p-2">{text}</p>;
    }
    if (state === "none") {
        return <p className="text-[11px] text-[#525252] mt-1 italic">Plain-language explainer isn’t available right now.</p>;
    }
    return (
        <button
            onClick={explain}
            disabled={state === "loading"}
            className="mt-1 flex items-center gap-1 text-[11px] text-[#737373] hover:text-[var(--accent)] transition-colors disabled:opacity-60"
        >
            <Info className="w-3 h-3" />
            {state === "loading" ? "Explaining…" : "Explain this to me"}
        </button>
    );
}
