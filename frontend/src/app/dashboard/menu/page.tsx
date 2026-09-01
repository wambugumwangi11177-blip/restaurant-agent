"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
import { motion, AnimatePresence } from "framer-motion";
import {
    UtensilsCrossed,
    Plus,
    X,
    TrendingUp,
    TrendingDown,
    Minus,
    Layers,
    DollarSign,
    Percent,
    ChefHat,
    Check,
    Edit3,
    Trash2,
    Save,
    AlertTriangle,
    Search,
    BookOpen,
} from "lucide-react";

interface ModifierOption {
    id: number;
    name: string;
    price_delta_cents: number;
    is_available: boolean;
}

interface ModifierGroup {
    id: number;
    name: string;
    min_selection: number;
    max_selection: number;
    is_required: boolean;
    options: ModifierOption[];
}

interface RecipeIngredient {
    id: number;
    menu_item_id: number;
    inventory_item_id: number;
    item_name: string;
    unit: string;
    cost_per_unit: number;
    quantity_per_serving: number;
    is_critical: boolean;
}

interface MenuItem {
    id: number;
    restaurant_id: number;
    name: string;
    description: string;
    price: number; // in cents
    cost_price: number;
    effective_cost_cents: number;
    food_cost_percent: number;
    margin_percent: number;
    category: string;
    image_url: string;
    is_available: boolean;
    prep_station: string;
    avg_prep_minutes: number;
    modifier_groups: ModifierGroup[];
    recipe_count: number;
}

interface InventoryItem {
    id: number;
    item_name: string;
    unit: string;
    cost_per_unit: number;
}

export default function MenuPage() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [inventoryItems, setInventoryItems] = useState<InventoryItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedCategory, setSelectedCategory] = useState("All");

    // Bulk selection state
    const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);

    // Detail / Edit Drawer state
    const [drawerItem, setDrawerItem] = useState<MenuItem | null>(null);
    const [activeTab, setActiveTab] = useState<"details" | "recipe" | "modifiers">("details");

    // Recipe editing in drawer
    const [recipeIngredients, setRecipeIngredients] = useState<RecipeIngredient[]>([]);
    const [addingIngredientId, setAddingIngredientId] = useState<number | null>(null);
    const [addingQty, setAddingQty] = useState<number>(0.1);

    // Modifier editing in drawer
    const [allModifierGroups, setAllModifierGroups] = useState<ModifierGroup[]>([]);
    const [attachingGroupId, setAttachingGroupId] = useState<number | null>(null);

    // New item form modal
    const [showNewItemModal, setShowNewItemModal] = useState(false);
    const [newItemForm, setNewItemForm] = useState({
        name: "",
        category: "Mains",
        priceKES: 500,
        costKES: 150,
        prepStation: "main",
        avgPrepMinutes: 10,
        description: "",
    });

    const fetchData = useCallback(async () => {
        try {
            const [menuRes, invRes, modRes] = await Promise.all([
                api.get("/menu/"),
                api.get("/inventory/"),
                api.get("/menu/modifiers/groups").catch(() => ({ data: [] })),
            ]);
            setItems(Array.isArray(menuRes.data) ? menuRes.data : []);
            setInventoryItems(Array.isArray(invRes.data) ? invRes.data : []);
            setAllModifierGroups(Array.isArray(modRes.data) ? modRes.data : []);
        } catch {}
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const categories = useMemo(() => ["All", ...Array.from(new Set(items.map((i) => i.category)))], [items]);

    const filteredItems = useMemo(() => {
        return items.filter((i) => {
            const matchesCat = selectedCategory === "All" || i.category === selectedCategory;
            const matchesSearch =
                !searchQuery.trim() ||
                i.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                i.category.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesCat && matchesSearch;
        });
    }, [items, selectedCategory, searchQuery]);

    // Open item drawer
    const handleOpenDrawer = async (item: MenuItem) => {
        setDrawerItem(item);
        setActiveTab("details");
        try {
            const recipeRes = await api.get(`/menu/${item.id}/recipe`);
            setRecipeIngredients(Array.isArray(recipeRes.data) ? recipeRes.data : []);
        } catch {
            setRecipeIngredients([]);
        }
    };

    // Save Item Details
    const handleSaveItemDetails = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!drawerItem) return;
        try {
            await api.put(`/menu/${drawerItem.id}`, {
                name: drawerItem.name,
                category: drawerItem.category,
                price: drawerItem.price,
                cost_price: drawerItem.cost_price,
                description: drawerItem.description,
            });
            await fetchData();
            alert("Item updated successfully");
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not save item");
        }
    };

    // Add Recipe Ingredient
    const handleAddIngredient = async () => {
        if (!drawerItem || !addingIngredientId || addingQty <= 0) return;
        try {
            await api.post(`/menu/${drawerItem.id}/recipe`, {
                inventory_item_id: addingIngredientId,
                quantity_per_serving: addingQty,
                is_critical: true,
            });
            const recipeRes = await api.get(`/menu/${drawerItem.id}/recipe`);
            setRecipeIngredients(recipeRes.data);
            setAddingIngredientId(null);
            setAddingQty(0.1);
            await fetchData();
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not add ingredient");
        }
    };

    // Remove Recipe Ingredient
    const handleRemoveIngredient = async (ingredientId: number) => {
        if (!drawerItem) return;
        try {
            await api.delete(`/menu/${drawerItem.id}/recipe/${ingredientId}`);
            setRecipeIngredients((prev) => prev.filter((r) => r.id !== ingredientId));
            await fetchData();
        } catch {}
    };

    // Attach Modifier Group
    const handleAttachModifierGroup = async () => {
        if (!drawerItem || !attachingGroupId) return;
        try {
            await api.post(`/menu/${drawerItem.id}/modifiers/${attachingGroupId}`);
            await fetchData();
            setAttachingGroupId(null);
        } catch {}
    };

    // Bulk 86 actions
    const handleBulk86 = async (isAvailable: boolean) => {
        if (selectedItemIds.length === 0) return;
        try {
            await api.post("/menu/bulk-86", {
                item_ids: selectedItemIds,
                is_available: isAvailable,
            });
            setSelectedItemIds([]);
            await fetchData();
        } catch {}
    };

    // Create New Item
    const handleCreateNewItem = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await api.post("/menu/", {
                name: newItemForm.name,
                category: newItemForm.category,
                price: Math.round(newItemForm.priceKES * 100),
                description: newItemForm.description,
            });
            setShowNewItemModal(false);
            setNewItemForm({
                name: "",
                category: "Mains",
                priceKES: 500,
                costKES: 150,
                prepStation: "main",
                avgPrepMinutes: 10,
                description: "",
            });
            await fetchData();
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not create item");
        }
    };

    return (
        <div className="flex h-[calc(100vh-4rem)] bg-stone-950 text-stone-100 overflow-hidden">
            {/* MAIN CATALOG VIEW */}
            <div className="flex-1 flex flex-col p-4 overflow-hidden border-r border-stone-800/80">
                {/* Header Toolbar */}
                <div className="flex items-center justify-between pb-3 border-b border-stone-800/80">
                    <div>
                        <h1 className="text-lg font-bold">Menu & Recipe Engineering</h1>
                        <p className="text-xs text-stone-400">
                            {items.length} items &bull; BOM stock links & food cost margins
                        </p>
                    </div>
                    <button
                        onClick={() => setShowNewItemModal(true)}
                        className="px-3.5 py-2 rounded-xl bg-amber-500 text-stone-950 font-bold text-xs hover:bg-amber-400 flex items-center gap-1.5 shadow-md shadow-amber-500/20"
                    >
                        <Plus className="w-3.5 h-3.5" /> Add Menu Item
                    </button>
                </div>

                {/* Filter and Bulk Bar */}
                <div className="flex flex-wrap items-center justify-between gap-3 py-3 border-b border-stone-800/80">
                    <div className="flex items-center gap-2 flex-1 max-w-md">
                        <div className="relative flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                            <input
                                type="text"
                                placeholder="Search dishes, drinks, ingredients..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full bg-stone-900 border border-stone-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-stone-100 focus:outline-none focus:border-amber-500/60"
                            />
                        </div>
                        <select
                            value={selectedCategory}
                            onChange={(e) => setSelectedCategory(e.target.value)}
                            className="bg-stone-900 border border-stone-800 rounded-lg px-2.5 py-1.5 text-xs text-stone-200"
                        >
                            {categories.map((c) => (
                                <option key={c} value={c}>
                                    {c}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Bulk Selection Actions */}
                    {selectedItemIds.length > 0 && (
                        <div className="flex items-center gap-2 bg-stone-900 border border-stone-800 px-3 py-1 rounded-xl">
                            <span className="text-xs font-semibold text-stone-300">{selectedItemIds.length} selected:</span>
                            <button
                                onClick={() => handleBulk86(false)}
                                className="text-xs font-bold text-red-400 hover:text-red-300 px-2 py-0.5 rounded bg-red-950/60 border border-red-900/60"
                            >
                                86 Items
                            </button>
                            <button
                                onClick={() => handleBulk86(true)}
                                className="text-xs font-bold text-emerald-400 hover:text-emerald-300 px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-900/60"
                            >
                                Available
                            </button>
                        </div>
                    )}
                </div>

                {/* Items Grid Table */}
                <div className="flex-1 overflow-y-auto pt-2 space-y-2">
                    {loading ? (
                        <div className="p-8 text-center text-xs text-stone-500">Loading menu...</div>
                    ) : filteredItems.length === 0 ? (
                        <div className="p-12 text-center text-xs text-stone-500">No menu items found.</div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                            {filteredItems.map((item) => {
                                const isSelected = selectedItemIds.includes(item.id);
                                const isDrawerOpen = drawerItem?.id === item.id;
                                return (
                                    <div
                                        key={item.id}
                                        onClick={() => handleOpenDrawer(item)}
                                        className={`p-3.5 rounded-xl border flex flex-col justify-between cursor-pointer transition-all ${
                                            isDrawerOpen
                                                ? "bg-amber-500/10 border-amber-500/80 shadow-md"
                                                : "bg-stone-900/70 border-stone-800 hover:border-stone-700"
                                        }`}
                                    >
                                        <div>
                                            <div className="flex items-start justify-between gap-1 mb-1">
                                                <div className="flex items-center gap-2">
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={(e) => {
                                                            e.stopPropagation();
                                                            setSelectedItemIds((prev) =>
                                                                prev.includes(item.id)
                                                                    ? prev.filter((id) => id !== item.id)
                                                                    : [...prev, item.id]
                                                            );
                                                        }}
                                                        className="rounded bg-stone-950 border-stone-700 text-amber-500"
                                                    />
                                                    <h3 className="text-sm font-semibold text-stone-100">{item.name}</h3>
                                                </div>
                                                <span
                                                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                                                        item.is_available
                                                            ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                                                            : "bg-red-950 text-red-400 border-red-800"
                                                    }`}
                                                >
                                                    {item.is_available ? "Live" : "86'd"}
                                                </span>
                                            </div>
                                            {item.description && (
                                                <p className="text-[11px] text-stone-400 line-clamp-2 mb-2">{item.description}</p>
                                            )}
                                        </div>

                                        {/* Financial & Recipe Badges */}
                                        <div className="pt-2 border-t border-stone-800/60 mt-2 space-y-1.5">
                                            <div className="flex justify-between items-center text-xs">
                                                <span className="font-bold text-amber-400">{formatKES(item.price)}</span>
                                                <span className="text-[11px] text-stone-400">
                                                    Cost: {formatKES(item.effective_cost_cents)}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center text-[10px] font-semibold">
                                                <span
                                                    className={`px-1.5 py-0.5 rounded ${
                                                        item.food_cost_percent <= 32
                                                            ? "bg-emerald-950/80 text-emerald-400"
                                                            : item.food_cost_percent <= 40
                                                            ? "bg-amber-950/80 text-amber-300"
                                                            : "bg-red-950/80 text-red-400"
                                                    }`}
                                                >
                                                    {item.food_cost_percent}% Food Cost
                                                </span>
                                                <span className="text-stone-400">
                                                    {item.recipe_count} ingredients &bull; {item.modifier_groups.length} mod groups
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* RIGHT: ITEM RECIPE & MODIFIER DRAWER */}
            {drawerItem && (
                <div className="w-96 lg:w-[440px] bg-stone-900 border-l border-stone-800 flex flex-col overflow-hidden">
                    {/* Drawer Header */}
                    <div className="p-4 border-b border-stone-800 flex items-center justify-between bg-stone-900/90">
                        <div>
                            <h3 className="text-sm font-bold text-stone-100">{drawerItem.name}</h3>
                            <p className="text-[11px] text-stone-400">{drawerItem.category} &bull; {formatKES(drawerItem.price)}</p>
                        </div>
                        <button onClick={() => setDrawerItem(null)} className="text-stone-400 hover:text-stone-200">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Tab Navigation */}
                    <div className="flex border-b border-stone-800 bg-stone-950/40">
                        <button
                            onClick={() => setActiveTab("details")}
                            className={`flex-1 py-2.5 text-xs font-semibold text-center border-b-2 ${
                                activeTab === "details"
                                    ? "border-amber-500 text-amber-400"
                                    : "border-transparent text-stone-400 hover:text-stone-200"
                            }`}
                        >
                            Item Details
                        </button>
                        <button
                            onClick={() => setActiveTab("recipe")}
                            className={`flex-1 py-2.5 text-xs font-semibold text-center border-b-2 ${
                                activeTab === "recipe"
                                    ? "border-amber-500 text-amber-400"
                                    : "border-transparent text-stone-400 hover:text-stone-200"
                            }`}
                        >
                            Recipe / BOM ({recipeIngredients.length})
                        </button>
                        <button
                            onClick={() => setActiveTab("modifiers")}
                            className={`flex-1 py-2.5 text-xs font-semibold text-center border-b-2 ${
                                activeTab === "modifiers"
                                    ? "border-amber-500 text-amber-400"
                                    : "border-transparent text-stone-400 hover:text-stone-200"
                            }`}
                        >
                            Modifiers ({drawerItem.modifier_groups.length})
                        </button>
                    </div>

                    {/* Drawer Tab Content */}
                    <div className="flex-1 overflow-y-auto p-4">
                        {activeTab === "details" && (
                            <form onSubmit={handleSaveItemDetails} className="space-y-3">
                                <div>
                                    <label className="text-xs text-stone-400 block mb-1">Item Name</label>
                                    <input
                                        type="text"
                                        value={drawerItem.name}
                                        onChange={(e) => setDrawerItem({ ...drawerItem, name: e.target.value })}
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                    />
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <div>
                                        <label className="text-xs text-stone-400 block mb-1">Sale Price (KES)</label>
                                        <input
                                            type="number"
                                            value={drawerItem.price / 100}
                                            onChange={(e) =>
                                                setDrawerItem({ ...drawerItem, price: Math.round(Number(e.target.value) * 100) })
                                            }
                                            className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs text-stone-400 block mb-1">Category</label>
                                        <input
                                            type="text"
                                            value={drawerItem.category}
                                            onChange={(e) => setDrawerItem({ ...drawerItem, category: e.target.value })}
                                            className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                        />
                                    </div>
                                </div>
                                <div>
                                    <label className="text-xs text-stone-400 block mb-1">Description</label>
                                    <textarea
                                        rows={3}
                                        value={drawerItem.description || ""}
                                        onChange={(e) => setDrawerItem({ ...drawerItem, description: e.target.value })}
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                    />
                                </div>

                                <div className="p-3 bg-stone-950 rounded-xl border border-stone-800 space-y-1 text-xs">
                                    <div className="flex justify-between text-stone-400">
                                        <span>Effective Cost:</span>
                                        <span className="font-bold text-stone-200">{formatKES(drawerItem.effective_cost_cents)}</span>
                                    </div>
                                    <div className="flex justify-between text-stone-400">
                                        <span>Contribution Margin:</span>
                                        <span className="font-bold text-emerald-400">
                                            {formatKES(drawerItem.price - drawerItem.effective_cost_cents)} ({drawerItem.margin_percent}%)
                                        </span>
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    className="w-full py-2.5 rounded-xl bg-amber-500 text-stone-950 font-bold text-xs hover:bg-amber-400 flex items-center justify-center gap-1.5"
                                >
                                    <Save className="w-3.5 h-3.5" /> Save Changes
                                </button>
                            </form>
                        )}

                        {activeTab === "recipe" && (
                            <div className="space-y-4">
                                <p className="text-xs text-stone-400">
                                    Link raw inventory items to this dish for automatic stock depletion on orders and live food cost calculation.
                                </p>

                                {/* Ingredients List */}
                                <div className="space-y-2">
                                    {recipeIngredients.length === 0 ? (
                                        <div className="p-6 text-center text-xs text-stone-500 bg-stone-950/60 rounded-xl border border-stone-800">
                                            No recipe ingredients linked yet.
                                        </div>
                                    ) : (
                                        recipeIngredients.map((r) => (
                                            <div
                                                key={r.id}
                                                className="p-2.5 bg-stone-950 rounded-xl border border-stone-800 flex items-center justify-between text-xs"
                                            >
                                                <div>
                                                    <span className="font-semibold text-stone-200 block">{r.item_name}</span>
                                                    <span className="text-[10px] text-stone-500">
                                                        {r.quantity_per_serving} {r.unit} &bull; Cost: KES {r.cost_per_unit}/unit
                                                    </span>
                                                </div>
                                                <button
                                                    onClick={() => handleRemoveIngredient(r.id)}
                                                    className="text-stone-500 hover:text-red-400 p-1"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        ))
                                    )}
                                </div>

                                {/* Add Ingredient Widget */}
                                <div className="p-3 bg-stone-950 rounded-xl border border-stone-800 space-y-2">
                                    <h4 className="text-xs font-bold text-stone-300">Add Ingredient to Recipe</h4>
                                    <select
                                        value={addingIngredientId || ""}
                                        onChange={(e) => setAddingIngredientId(Number(e.target.value))}
                                        className="w-full bg-stone-900 border border-stone-800 rounded px-2.5 py-1.5 text-xs text-stone-200"
                                    >
                                        <option value="">Select inventory item...</option>
                                        {inventoryItems.map((inv) => (
                                            <option key={inv.id} value={inv.id}>
                                                {inv.item_name} ({inv.unit})
                                            </option>
                                        ))}
                                    </select>
                                    <div className="flex gap-2">
                                        <input
                                            type="number"
                                            step="0.01"
                                            placeholder="Qty per portion"
                                            value={addingQty || ""}
                                            onChange={(e) => setAddingQty(Number(e.target.value))}
                                            className="flex-1 bg-stone-900 border border-stone-800 rounded px-2.5 py-1.5 text-xs text-stone-200"
                                        />
                                        <button
                                            onClick={handleAddIngredient}
                                            disabled={!addingIngredientId}
                                            className="px-3 py-1.5 bg-amber-500 text-stone-950 font-bold text-xs rounded hover:bg-amber-400 disabled:opacity-40"
                                        >
                                            Add
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {activeTab === "modifiers" && (
                            <div className="space-y-4">
                                <p className="text-xs text-stone-400">
                                    Modifier groups attached to this item appear on the POS screen when tapped.
                                </p>

                                <div className="space-y-2">
                                    {drawerItem.modifier_groups.map((mg) => (
                                        <div key={mg.id} className="p-3 bg-stone-950 rounded-xl border border-stone-800 space-y-1.5">
                                            <div className="flex justify-between items-center">
                                                <span className="text-xs font-bold text-stone-200">{mg.name}</span>
                                                <button
                                                    onClick={async () => {
                                                        await api.delete(`/menu/${drawerItem.id}/modifiers/${mg.id}`);
                                                        await fetchData();
                                                    }}
                                                    className="text-[10px] text-red-400 hover:underline"
                                                >
                                                    Detach
                                                </button>
                                            </div>
                                            <div className="flex flex-wrap gap-1">
                                                {mg.options.map((opt) => (
                                                    <span key={opt.id} className="text-[10px] bg-stone-900 text-stone-300 px-1.5 py-0.5 rounded">
                                                        {opt.name} (+{formatKES(opt.price_delta_cents)})
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="p-3 bg-stone-950 rounded-xl border border-stone-800 space-y-2">
                                    <h4 className="text-xs font-bold text-stone-300">Attach Modifier Group</h4>
                                    <div className="flex gap-2">
                                        <select
                                            value={attachingGroupId || ""}
                                            onChange={(e) => setAttachingGroupId(Number(e.target.value))}
                                            className="flex-1 bg-stone-900 border border-stone-800 rounded px-2.5 py-1.5 text-xs text-stone-200"
                                        >
                                            <option value="">Select group to attach...</option>
                                            {allModifierGroups.map((g) => (
                                                <option key={g.id} value={g.id}>
                                                    {g.name}
                                                </option>
                                            ))}
                                        </select>
                                        <button
                                            onClick={handleAttachModifierGroup}
                                            disabled={!attachingGroupId}
                                            className="px-3 py-1.5 bg-amber-500 text-stone-950 font-bold text-xs rounded hover:bg-amber-400 disabled:opacity-40"
                                        >
                                            Attach
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* NEW ITEM MODAL */}
            {showNewItemModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-stone-100">Add New Menu Item</h3>
                            <button onClick={() => setShowNewItemModal(false)} className="text-stone-400">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <form onSubmit={handleCreateNewItem} className="space-y-3">
                            <div>
                                <label className="text-xs text-stone-400 block mb-1">Item Name</label>
                                <input
                                    type="text"
                                    required
                                    placeholder="e.g. Swahili Coconut Fish"
                                    value={newItemForm.name}
                                    onChange={(e) => setNewItemForm({ ...newItemForm, name: e.target.value })}
                                    className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-xs text-stone-400 block mb-1">Sale Price (KES)</label>
                                    <input
                                        type="number"
                                        required
                                        value={newItemForm.priceKES || ""}
                                        onChange={(e) => setNewItemForm({ ...newItemForm, priceKES: Number(e.target.value) })}
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-stone-400 block mb-1">Category</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="Mains, Drinks, Sides"
                                        value={newItemForm.category}
                                        onChange={(e) => setNewItemForm({ ...newItemForm, category: e.target.value })}
                                        className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs text-stone-400 block mb-1">Description</label>
                                <textarea
                                    rows={2}
                                    value={newItemForm.description}
                                    onChange={(e) => setNewItemForm({ ...newItemForm, description: e.target.value })}
                                    className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100"
                                />
                            </div>
                            <div className="flex gap-2 pt-2 border-t border-stone-800">
                                <button
                                    type="button"
                                    onClick={() => setShowNewItemModal(false)}
                                    className="flex-1 py-2 rounded-xl border border-stone-700 text-xs text-stone-400"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 py-2 rounded-xl bg-amber-500 text-stone-950 font-bold text-xs hover:bg-amber-400"
                                >
                                    Create Item
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
