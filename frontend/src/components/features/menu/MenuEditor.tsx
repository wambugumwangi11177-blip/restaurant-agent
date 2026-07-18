"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { UtensilsCrossed, Plus, X, Loader2, TrendingUp, TrendingDown, ChefHat, Trash2, Check } from "lucide-react";

interface MenuItem {
    id: number;
    name: string;
    description: string;
    price: number;
    category: string;
    is_available: boolean;
}

/**
 * Full menu CRUD + recipe editor + AI menu engineering — extracted from the
 * original dashboard/menu/page.tsx unmodified. Reused as-is by every tier
 * with `menu` = RW (directive 015: Owner, Manager) — other tiers with
 * `menu` = R get MenuReadView instead, not this editor.
 */
export default function MenuEditor() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({ name: "", price: "", category: "", description: "" });
    const [toast, setToast] = useState("");

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    // Recipe editor (directive 017) — what a dish is made of, the
    // prerequisite for auto-deducting stock when it sells.
    const [inventoryItems, setInventoryItems] = useState<any[]>([]);
    const [recipeOpenId, setRecipeOpenId] = useState<number | null>(null);
    const [ingredientsByItem, setIngredientsByItem] = useState<Record<number, any[]>>({});
    const [newIngredientId, setNewIngredientId] = useState("");
    const [newIngredientQty, setNewIngredientQty] = useState("");
    const [recipeSaving, setRecipeSaving] = useState(false);

    useEffect(() => {
        Promise.all([
            api.get("/menu/").catch(() => ({ data: [] })),
            api.get("/ai/menu-engineering").catch(() => ({ data: null })),
            api.get("/inventory/").catch(() => ({ data: [] })),
        ]).then(([menuRes, aiRes, invRes]) => {
            setItems(menuRes.data || []);
            setAiData(aiRes.data);
            setInventoryItems(Array.isArray(invRes.data) ? invRes.data : []);
            setLoading(false);
        });
    }, []);

    const fetchIngredients = async (itemId: number) => {
        try {
            const res = await api.get(`/menu/${itemId}/ingredients`);
            setIngredientsByItem((prev) => ({ ...prev, [itemId]: res.data }));
        } catch { }
    };

    const toggleRecipe = (itemId: number) => {
        if (recipeOpenId === itemId) {
            setRecipeOpenId(null);
            return;
        }
        setRecipeOpenId(itemId);
        setNewIngredientId(""); setNewIngredientQty("");
        if (!ingredientsByItem[itemId]) fetchIngredients(itemId);
    };

    const handleAddIngredient = async (itemId: number) => {
        if (!newIngredientId || !newIngredientQty) return;
        setRecipeSaving(true);
        try {
            await api.post(`/menu/${itemId}/ingredients`, {
                inventory_item_id: parseInt(newIngredientId),
                quantity_per_serving: parseFloat(newIngredientQty),
            });
            setNewIngredientId(""); setNewIngredientQty("");
            await fetchIngredients(itemId);
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to add ingredient");
        }
        setRecipeSaving(false);
    };

    const handleRemoveIngredient = async (itemId: number, ingredientId: number) => {
        try {
            await api.delete(`/menu/${itemId}/ingredients/${ingredientId}`);
            await fetchIngredients(itemId);
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to remove ingredient");
        }
    };

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
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to add item");
        }
        setSaving(false);
    };

    const toggleAvailability = async (item: MenuItem) => {
        try {
            await api.put(`/menu/${item.id}`, { is_available: !item.is_available });
            fetchMenu();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to update availability");
        }
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
            Star: "bg-[var(--success)]/10 text-[var(--success)]",
            Plowhorse: "bg-[var(--warning)]/10 text-[var(--warning)]",
            Puzzle: "bg-[#3b82f6]/10 text-[#3b82f6]",
            Dog: "bg-[var(--danger)]/10 text-[var(--danger)]",
        };
        return map[c] || "bg-[var(--text-muted)]/10 text-[var(--text-muted)]";
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[var(--surface)] rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[var(--success)]/10 border border-[var(--success)]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[var(--success)]" />
                        <span className="text-sm text-[var(--success)]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[var(--text)]">Your Menu</h1>
                    <p className="text-sm text-[var(--text-dim)] mt-0.5">
                        {items.length} item{items.length !== 1 ? "s" : ""} · synced with your POS
                    </p>
                </div>
                <button onClick={() => setShowForm(!showForm)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--bg)] text-sm font-medium transition-colors">
                    {showForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                    {showForm ? "Cancel" : "Add Item"}
                </button>
            </div>

            {/* What we found about your menu */}
            {(summary.stars > 0 || summary.dogs > 0 || recommendations.length > 0) && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)]">
                        <p className="text-xs font-semibold text-[var(--text)]">What we found about your menu</p>
                    </div>
                    {/* Performance summary */}
                    <div className="px-4 py-3 flex flex-wrap gap-2">
                        {summary.stars > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[var(--success)]/10 text-[var(--success)] flex items-center gap-1">
                                <TrendingUp className="w-3 h-3" /> {summary.stars} top seller{summary.stars > 1 ? "s" : ""}
                            </span>
                        )}
                        {summary.puzzles > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[#3b82f6]/10 text-[#3b82f6]">
                                {summary.puzzles} hidden gem{summary.puzzles > 1 ? "s" : ""} — profitable but not selling enough
                            </span>
                        )}
                        {summary.plowhorses > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[var(--warning)]/10 text-[var(--warning)]">
                                {summary.plowhorses} popular but thin margin
                            </span>
                        )}
                        {summary.dogs > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[var(--danger)]/10 text-[var(--danger)] flex items-center gap-1">
                                <TrendingDown className="w-3 h-3" /> {summary.dogs} slow mover{summary.dogs > 1 ? "s" : ""} — think about removing
                            </span>
                        )}
                        {summary.avg_food_cost_pct > 0 && (
                            <span className="text-[10px] px-2 py-1 rounded-full bg-[var(--text-muted)]/10 text-[var(--text-muted)]">
                                Food costs around {summary.avg_food_cost_pct.toFixed(0)}% of your prices
                            </span>
                        )}
                    </div>
                    {/* Suggestions */}
                    {recommendations.length > 0 && (
                        <div className="px-4 pb-3 space-y-2">
                            <p className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">Suggestions</p>
                            {recommendations.slice(0, 3).map((rec: any, i: number) => (
                                <div key={i} className="flex items-start gap-2 text-xs">
                                    <span className="text-[var(--accent)] mt-0.5">💡</span>
                                    <div>
                                        <p className="text-[var(--text)]">{friendlyRec(rec.reason || rec.message)}</p>
                                        {rec.action && <p className="text-[var(--text-dim)] mt-0.5">{rec.action}</p>}
                                        {rec.estimated_impact && (
                                            <p className="text-[10px] text-[var(--success)] mt-0.5">Could mean {rec.estimated_impact}</p>
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
                    className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 space-y-3">
                    <p className="text-sm text-[var(--text)] font-medium">New Menu Item</p>
                    <div className="grid grid-cols-2 gap-3">
                        <input type="text" placeholder="Name (e.g. Nyama Choma)" value={form.name}
                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--border)] focus:border-[var(--accent)] outline-none text-sm text-[var(--text)] placeholder-[var(--text-dim)]" required />
                        <input type="number" placeholder="Price in KES" value={form.price}
                            onChange={(e) => setForm({ ...form, price: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--border)] focus:border-[var(--accent)] outline-none text-sm text-[var(--text)] placeholder-[var(--text-dim)]" required />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <input type="text" placeholder="Category (e.g. Mains, Drinks)" value={form.category}
                            onChange={(e) => setForm({ ...form, category: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--border)] focus:border-[var(--accent)] outline-none text-sm text-[var(--text)] placeholder-[var(--text-dim)]" />
                        <input type="text" placeholder="Short description" value={form.description}
                            onChange={(e) => setForm({ ...form, description: e.target.value })}
                            className="px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--border)] focus:border-[var(--accent)] outline-none text-sm text-[var(--text)] placeholder-[var(--text-dim)]" />
                    </div>
                    <button type="submit" disabled={saving}
                        className="px-4 py-2 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--bg)] text-sm font-medium disabled:opacity-50 flex items-center gap-2 transition-colors">
                        {saving && <Loader2 className="w-3 h-3 animate-spin" />} Add to Menu
                    </button>
                </motion.form>
            )}

            {/* Menu Items by Category */}
            {items.length === 0 ? (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center">
                    <UtensilsCrossed className="w-8 h-8 text-[#333] mx-auto mb-3" />
                    <p className="text-sm text-[var(--text-dim)]">Your menu is empty. Add your first item above.</p>
                </div>
            ) : (
                <div className="space-y-5">
                    {categories.map((cat) => (
                        <div key={cat}>
                            <h3 className="text-xs font-semibold text-[var(--text-dim)] uppercase tracking-wider mb-2 px-1">{cat}</h3>
                            <div className="space-y-1">
                                {items.filter((i) => i.category === cat).map((item, idx) => {
                                    const aiItem = matrix.find((m: any) => m.item_id === item.id);
                                    const recipeOpen = recipeOpenId === item.id;
                                    const ingredients = ingredientsByItem[item.id] || [];
                                    const hasRecipe = ingredients.length > 0;
                                    return (
                                        <motion.div key={item.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                            transition={{ delay: idx * 0.03 }}
                                            className="bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden hover:border-[#333] transition-colors">
                                            <div className="px-4 py-3 flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    {aiItem && (
                                                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${classColor(aiItem.classification)}`}>
                                                            {classLabel(aiItem.classification)}
                                                        </span>
                                                    )}
                                                    <div>
                                                        <p className={`text-sm font-medium ${item.is_available ? "text-[var(--text)]" : "text-[var(--text-dim)] line-through"}`}>
                                                            {item.name}
                                                        </p>
                                                        {item.description && (
                                                            <p className="text-xs text-[var(--text-dim)] mt-0.5">{item.description}</p>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    {aiItem?.margin_pct !== undefined && (
                                                        <span className={`text-[10px] ${aiItem.margin_pct >= 60 ? "text-[var(--success)]" : aiItem.margin_pct >= 30 ? "text-[var(--text-muted)]" : "text-[var(--danger)]"
                                                            }`}>{aiItem.margin_pct.toFixed(0)}% profit</span>
                                                    )}
                                                    <span className="text-sm font-semibold text-[var(--accent)]">
                                                        KES {(item.price / 100).toLocaleString()}
                                                    </span>
                                                    <button onClick={() => toggleRecipe(item.id)}
                                                        title="Recipe — what this dish is made of"
                                                        className={`text-[10px] px-2 py-1 rounded flex items-center gap-1 transition-all ${recipeOpen ? "bg-[var(--accent)]/10 text-[var(--accent)]" : "bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)]"}`}>
                                                        <ChefHat className="w-3 h-3" />
                                                        Recipe
                                                    </button>
                                                    <button onClick={() => toggleAvailability(item)}
                                                        role="switch"
                                                        aria-checked={item.is_available}
                                                        aria-label={`Mark ${item.name} as ${item.is_available ? "unavailable" : "available"}`}
                                                        className={`w-8 h-5 rounded-full relative transition-colors ${item.is_available ? "bg-[var(--success)]" : "bg-[#333]"}`}>
                                                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${item.is_available ? "left-3.5" : "left-0.5"}`} />
                                                    </button>
                                                </div>
                                            </div>

                                            {recipeOpen && (
                                                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                                                    className="border-t border-[var(--surface-hover)] px-4 py-3 bg-[#0f0f0f] space-y-2">
                                                    {!hasRecipe && (
                                                        <p className="text-[11px] text-[var(--warning)]">
                                                            No recipe set — this dish's sales won't deduct stock until you add ingredients.
                                                        </p>
                                                    )}
                                                    {ingredients.map((ing) => (
                                                        <div key={ing.id} className="flex items-center justify-between text-xs">
                                                            <span className="text-[var(--text)]">{ing.item_name}</span>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-[var(--text-muted)]">{ing.quantity_per_serving} {ing.unit} / serving</span>
                                                                <button onClick={() => handleRemoveIngredient(item.id, ing.id)}
                                                                    aria-label={`Remove ${ing.item_name}`}
                                                                    className="text-[var(--text-dim)] hover:text-[var(--danger)] transition-colors">
                                                                    <Trash2 className="w-3 h-3" />
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ))}
                                                    <div className="flex gap-2 items-center pt-2">
                                                        <select value={newIngredientId} onChange={(e) => setNewIngredientId(e.target.value)}
                                                            className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                                            <option value="">Add ingredient…</option>
                                                            {inventoryItems.map((inv) => (
                                                                <option key={inv.id} value={inv.id}>{inv.item_name} ({inv.unit})</option>
                                                            ))}
                                                        </select>
                                                        <input placeholder="Qty / serving" value={newIngredientQty}
                                                            onChange={(e) => setNewIngredientQty(e.target.value)} type="number"
                                                            className="w-28 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                        <button onClick={() => handleAddIngredient(item.id)} disabled={!newIngredientId || !newIngredientQty || recipeSaving}
                                                            className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                            {recipeSaving ? "..." : "Add"}
                                                        </button>
                                                    </div>
                                                </motion.div>
                                            )}
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
