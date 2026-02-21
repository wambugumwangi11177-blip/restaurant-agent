"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { UtensilsCrossed, Plus, X, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface MenuItem {
    id: number;
    name: string;
    description: string;
    price: number;
    category: string;
    is_available: boolean;
}

export default function MenuPage() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({ name: "", price: "", category: "", description: "" });

    useEffect(() => {
        Promise.all([
            api.get("/menu/").catch(() => ({ data: [] })),
            api.get("/ai/menu-engineering").catch(() => ({ data: null })),
        ]).then(([menuRes, aiRes]) => {
            setItems(menuRes.data || []);
            setAiData(aiRes.data);
            setLoading(false);
        });
    }, []);

    const fetchMenu = () => {
        api.get("/menu/").then((r) => setItems(r.data)).catch(() => { });
    };

    const handleAdd = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post("/menu/", {
                name: form.name,
                price: Math.round(parseFloat(form.price) * 100),
                category: form.category,
                description: form.description,
            });
            setForm({ name: "", price: "", category: "", description: "" });
            setShowForm(false);
            fetchMenu();
        } catch { }
        setSaving(false);
    };

    const toggleAvailability = async (item: MenuItem) => {
        try {
            await api.put(`/menu/${item.id}`, { is_available: !item.is_available });
            fetchMenu();
        } catch { }
    };

    const categories = [...new Set(items.map((i) => i.category).filter(Boolean))];
    const matrix = aiData?.matrix || [];
    const recommendations = aiData?.recommendations || [];
    const summary = aiData?.summary || {};

    // Friendly classification labels
    const classLabel = (c: string) => {
        const map: Record<string, string> = {
            Star: "Top Seller",
            Plowhorse: "Popular",
            Puzzle: "Hidden Gem",
            Dog: "Slow Mover",
        };
        return map[c] || c;
    };

    const classColor = (c: string) => {
        const map: Record<string, string> = {
            Star: "bg-[#22c55e]/10 text-[#22c55e]",
            Plowhorse: "bg-[#eab308]/10 text-[#eab308]",
            Puzzle: "bg-[#3b82f6]/10 text-[#3b82f6]",
            Dog: "bg-[#ef4444]/10 text-[#ef4444]",
        };
        return map[c] || "bg-[#737373]/10 text-[#737373]";
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Your Menu</h1>
                    <p className="text-sm text-[#525252] mt-0.5">
                        {items.length} item{items.length !== 1 ? "s" : ""} · synced with your POS
                    </p>
                </div>
                <button onClick={() => setShowForm(!showForm)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#d4a853] hover:bg-[#e0b96a] text-[#0a0a0a] text-sm font-medium transition-colors">
                    {showForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                    {showForm ? "Cancel" : "Add Item"}
                </button>
            </div>

            {/* What we found about your menu */}
            {(summary.stars > 0 || summary.dogs > 0 || recommendations.length > 0) && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a]">
                        <p className="text-xs font-semibold text-[#e5e5e5]">What we found about your menu</p>
                    </div>
                    {/* Performance summary */}
                    <div className="px-4 py-3 flex flex-wrap gap-2">
                        {summary.stars > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#22c55e]/10 text-[#22c55e] flex items-center gap-1">
                                <TrendingUp className="w-3 h-3" /> {summary.stars} top seller{summary.stars > 1 ? "s" : ""}
                            </span>
                        )}
                        {summary.puzzles > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#3b82f6]/10 text-[#3b82f6]">
                                {summary.puzzles} hidden gem{summary.puzzles > 1 ? "s" : ""} — profitable but not selling enough
                            </span>
                        )}
                        {summary.plowhorses > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#eab308]/10 text-[#eab308]">
                                {summary.plowhorses} popular but thin margin
                            </span>
                        )}
                        {summary.dogs > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#ef4444]/10 text-[#ef4444] flex items-center gap-1">
                                <TrendingDown className="w-3 h-3" /> {summary.dogs} slow mover{summary.dogs > 1 ? "s" : ""} — think about removing
                            </span>
                        )}
                        {summary.avg_food_cost_pct > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#737373]/10 text-[#737373]">
                                Food costs around {summary.avg_food_cost_pct.toFixed(0)}% of your prices
                            </span>
                        )}
                    </div>
                    {/* Suggestions */}
                    {recommendations.length > 0 && (
                        <div className="px-4 pb-3 space-y-2">
                            <p className="text-[10px] text-[#525252] uppercase tracking-wider">Suggestions</p>
                            {recommendations.slice(0, 3).map((rec: any, i: number) => (
                                <div key={i} className="flex items-start gap-2 text-xs">
                                    <span className="text-[#d4a853] mt-0.5">💡</span>
                                    <div>
                                        <p className="text-[#e5e5e5]">{friendlyRec(rec.reason || rec.message)}</p>
                                        {rec.action && <p className="text-[#525252] mt-0.5">{rec.action}</p>}
                                        {rec.estimated_impact && (
                                            <p className="text-[10px] text-[#22c55e] mt-0.5">Could mean {rec.estimated_impact}</p>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Add Form */}
            {showForm && (
                <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                    onSubmit={handleAdd}
                    className="bg-[#141414] border border-[#262626] rounded-xl p-5 space-y-3">
                    <p className="text-sm text-[#e5e5e5] font-medium">New Menu Item</p>
                    <div className="grid grid-cols-2 gap-3">
                        <input type="text" placeholder="Name (e.g. Nyama Choma)" value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-sm text-[#e5e5e5] placeholder-[#525252]" required />
                        <input type="number" placeholder="Price in KES" value={form.price}
                            onChange={(e) => setForm({ ...form, price: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-sm text-[#e5e5e5] placeholder-[#525252]" required />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <input type="text" placeholder="Category (e.g. Mains, Drinks)" value={form.category}
                            onChange={(e) => setForm({ ...form, category: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-sm text-[#e5e5e5] placeholder-[#525252]" />
                        <input type="text" placeholder="Short description" value={form.description}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-sm text-[#e5e5e5] placeholder-[#525252]" />
                    </div>
                    <button type="submit" disabled={saving}
                        className="px-4 py-2 rounded-lg bg-[#d4a853] hover:bg-[#e0b96a] text-[#0a0a0a] text-sm font-medium disabled:opacity-50 flex items-center gap-2 transition-colors">
                        {saving && <Loader2 className="w-3 h-3 animate-spin" />} Add to Menu
                    </button>
                </motion.form>
            )}

            {/* Menu Items by Category */}
            {items.length === 0 ? (
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-8 text-center">
                    <UtensilsCrossed className="w-8 h-8 text-[#333] mx-auto mb-3" />
                    <p className="text-sm text-[#525252]">Your menu is empty. Add your first item above.</p>
                </div>
            ) : (
                <div className="space-y-5">
                    {categories.map((cat) => (
                        <div key={cat}>
                            <h3 className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-2 px-1">{cat}</h3>
                            <div className="space-y-1">
                                {items.filter((i) => i.category === cat).map((item, idx) => {
                                    const aiItem = matrix.find((m: any) => m.item_id === item.id);
                                    return (
                                        <motion.div key={item.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                            transition={{ delay: idx * 0.03 }}
                                            className="bg-[#141414] border border-[#262626] rounded-xl px-4 py-3 flex items-center justify-between hover:border-[#333] transition-colors">
                                            <div className="flex items-center gap-3">
                                                {aiItem && (
                                                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${classColor(aiItem.classification)}`}>
                                                        {classLabel(aiItem.classification)}
                                                    </span>
                                                )}
                                                <div>
                                                    <p className={`text-sm font-medium ${item.is_available ? "text-[#e5e5e5]" : "text-[#525252] line-through"}`}>
                                                        {item.name}
                                                    </p>
                                                    {item.description && (
                                                        <p className="text-xs text-[#525252] mt-0.5">{item.description}</p>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                {aiItem?.margin_pct !== undefined && (
                                                    <span className={`text-[10px] ${aiItem.margin_pct >= 60 ? "text-[#22c55e]" : aiItem.margin_pct >= 30 ? "text-[#737373]" : "text-[#ef4444]"
                                                        }`}>{aiItem.margin_pct.toFixed(0)}% profit</span>
                                                )}
                                                <span className="text-sm font-semibold text-[#d4a853]">
                                                    KES {(item.price / 100).toLocaleString()}
                                                </span>
                                                <button onClick={() => toggleAvailability(item)}
                                                    className={`w-8 h-5 rounded-full relative transition-colors ${item.is_available ? "bg-[#22c55e]" : "bg-[#333]"}`}>
                                                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${item.is_available ? "left-3.5" : "left-0.5"}`} />
                                                </button>
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function friendlyRec(text: string) {
    return text
        .replace(/Star/g, "top seller")
        .replace(/Plowhorse/g, "popular item")
        .replace(/Puzzle/g, "hidden gem")
        .replace(/Dog/g, "slow mover");
}
