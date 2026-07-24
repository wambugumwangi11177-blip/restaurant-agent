"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { UtensilsCrossed, Plus, X } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import MenuInsightsPanel from "./MenuInsightsPanel";
import AddMenuItemForm from "./AddMenuItemForm";
import MenuItemRow from "./MenuItemRow";
import { getErrorMessage } from "@/lib/errors";
import type { MenuItem, MenuAiData, RecipeIngredient, InventoryPickItem } from "./types";

/**
 * Full menu CRUD + recipe editor + AI menu engineering — extracted from the
 * original dashboard/menu/page.tsx unmodified. Reused as-is by every tier
 * with `menu` = RW (directive 015: Owner, Manager) — other tiers with
 * `menu` = R get MenuReadView instead, not this editor.
 *
 * Split into MenuInsightsPanel (AI summary card), AddMenuItemForm (new item
 * form), and MenuItemRow (per-item availability/edit/recipe) to keep this
 * file focused on data fetching + the open/edit state that must stay lifted
 * here so only one item's edit form or recipe panel is open at a time.
 */
export default function MenuEditor() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [aiData, setAiData] = useState<MenuAiData | null>(null);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const { showToast, toastNode } = useToast();

    // Recipe editor (directive 017) — what a dish is made of, the
    // prerequisite for auto-deducting stock when it sells.
    const [inventoryItems, setInventoryItems] = useState<InventoryPickItem[]>([]);
    const [recipeOpenId, setRecipeOpenId] = useState<number | null>(null);
    const [ingredientsByItem, setIngredientsByItem] = useState<Record<number, RecipeIngredient[]>>({});
    const [newIngredientId, setNewIngredientId] = useState("");
    const [newIngredientQty, setNewIngredientQty] = useState("");
    const [recipeSaving, setRecipeSaving] = useState(false);

    // Edit item — name/price/category/description/prep time/photo URL.
    // Availability has its own dedicated toggle below; this covers everything else.
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editForm, setEditForm] = useState({ name: "", price: "", category: "", description: "", avg_prep_minutes: "", image_url: "" });
    const [editSaving, setEditSaving] = useState(false);

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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add ingredient"), "error");
        }
        setRecipeSaving(false);
    };

    const handleRemoveIngredient = async (itemId: number, ingredientId: number) => {
        try {
            await api.delete(`/menu/${itemId}/ingredients/${ingredientId}`);
            await fetchIngredients(itemId);
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to remove ingredient"), "error");
        }
    };

    const fetchMenu = () => {
        api.get("/menu/").then((r) => setItems(r.data)).catch(() => { });
    };

    const toggleAvailability = async (item: MenuItem) => {
        try {
            await api.put(`/menu/${item.id}`, { is_available: !item.is_available });
            fetchMenu();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update availability"), "error");
        }
    };

    const openEdit = (item: MenuItem) => {
        if (editingId === item.id) { setEditingId(null); return; }
        setEditingId(item.id);
        setEditForm({
            name: item.name,
            price: String(item.price / 100),
            category: item.category,
            description: item.description || "",
            avg_prep_minutes: item.avg_prep_minutes != null ? String(item.avg_prep_minutes) : "",
            image_url: item.image_url || "",
        });
    };

    const handleSaveEdit = async (itemId: number) => {
        setEditSaving(true);
        try {
            await api.put(`/menu/${itemId}`, {
                name: editForm.name,
                price: Math.round(parseFloat(editForm.price) * 100),
                category: editForm.category,
                description: editForm.description,
                avg_prep_minutes: editForm.avg_prep_minutes ? parseFloat(editForm.avg_prep_minutes) : undefined,
                image_url: editForm.image_url,
            });
            showToast("Saved");
            setEditingId(null);
            fetchMenu();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to save changes"), "error");
        }
        setEditSaving(false);
    };

    const categories = [...new Set(items.map((i) => i.category).filter(Boolean))];
    const matrix = aiData?.matrix || [];
    const recommendations = aiData?.recommendations || [];
    const summary = aiData?.summary || {
        stars: 0, dogs: 0, puzzles: 0, plowhorses: 0, avg_food_cost_pct: 0,
    };

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
            Star: "bg-success/10 text-success",
            Plowhorse: "bg-warning/10 text-warning",
            Puzzle: "bg-info/10 text-info",
            Dog: "bg-danger/10 text-danger",
        };
        return map[c] || "bg-text-muted/10 text-text-muted";
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-text">Your Menu</h1>
                    <p className="text-sm text-text-dim mt-0.5">
                        {items.length} item{items.length !== 1 ? "s" : ""} · synced with your POS
                    </p>
                </div>
                <button onClick={() => setShowForm(!showForm)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-accent hover:bg-accent-hover text-bg text-sm font-medium transition-colors">
                    {showForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                    {showForm ? "Cancel" : "Add Item"}
                </button>
            </div>

            <MenuInsightsPanel summary={summary} recommendations={recommendations} />

            {showForm && (
                <AddMenuItemForm
                    onAdded={fetchMenu}
                    onClose={() => setShowForm(false)}
                    showToast={showToast}
                />
            )}

            {/* Menu Items by Category */}
            {items.length === 0 ? (
                <div className="bg-surface border border-border rounded-xl p-8 text-center">
                    <UtensilsCrossed className="w-8 h-8 text-[#333] mx-auto mb-3" />
                    <p className="text-sm text-text-dim">Your menu is empty. Add your first item above.</p>
                </div>
            ) : (
                <div className="space-y-5">
                    {categories.map((cat) => (
                        <div key={cat}>
                            <h3 className="text-xs font-semibold text-text-dim uppercase tracking-wider mb-2 px-1">{cat}</h3>
                            <div className="space-y-1">
                                {items.filter((i) => i.category === cat).map((item, idx) => {
                                    const aiItem = matrix.find((m) => m.item_id === item.id)
                                        ?? { item_id: item.id, classification: "", margin_pct: 0 };
                                    return (
                                        <MenuItemRow
                                            key={item.id}
                                            item={item}
                                            idx={idx}
                                            aiItem={aiItem}
                                            classColor={classColor}
                                            classLabel={classLabel}
                                            editingId={editingId}
                                            openEdit={openEdit}
                                            editForm={editForm}
                                            setEditForm={setEditForm}
                                            setEditingId={setEditingId}
                                            handleSaveEdit={handleSaveEdit}
                                            editSaving={editSaving}
                                            recipeOpenId={recipeOpenId}
                                            toggleRecipe={toggleRecipe}
                                            ingredients={ingredientsByItem[item.id] || []}
                                            inventoryItems={inventoryItems}
                                            newIngredientId={newIngredientId}
                                            setNewIngredientId={setNewIngredientId}
                                            newIngredientQty={newIngredientQty}
                                            setNewIngredientQty={setNewIngredientQty}
                                            handleAddIngredient={handleAddIngredient}
                                            handleRemoveIngredient={handleRemoveIngredient}
                                            recipeSaving={recipeSaving}
                                            toggleAvailability={toggleAvailability}
                                        />
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
