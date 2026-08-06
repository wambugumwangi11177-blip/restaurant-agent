"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import api from "@/lib/api";
import { Plus, Trash2, Loader2, Check, AlertTriangle } from "lucide-react";

interface InventoryItemOption {
    id: number;
    item_name: string;
    unit: string;
    cost_per_unit: number;
}

interface RecipeLine {
    inventory_item_id: number;
    quantity_per_serving: string; // kept as string while editing, parsed on save
    is_critical: boolean;
}

interface Props {
    menuItemId: number;
    menuItemName: string;
    inventoryItems: InventoryItemOption[];
    onClose: () => void;
    onSaved?: (derivedCostPrice: number | null) => void;
}

// Recipes drive both stock deduction on every sale and (via sync_cost_price)
// the cost figure every margin/pricing number reads — so this is a
// money-moving edit in the same category as changing a price, matching the
// backend's own framing in routers/menu.py.
export default function RecipeEditor({ menuItemId, menuItemName, inventoryItems, onClose, onSaved }: Props) {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [lines, setLines] = useState<RecipeLine[]>([]);
    const [derivedCostPrice, setDerivedCostPrice] = useState<number | null>(null);
    const [storedCostPrice, setStoredCostPrice] = useState<number>(0);
    const [synced, setSynced] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        api.get(`/menu/${menuItemId}/recipe`).then((r) => {
            const data = r.data;
            setLines((data.ingredients || []).map((ing: any) => ({
                inventory_item_id: ing.inventory_item_id,
                quantity_per_serving: String(ing.quantity_per_serving),
                is_critical: ing.is_critical,
            })));
            setDerivedCostPrice(data.derived_cost_price);
            setStoredCostPrice(data.stored_cost_price);
            setSynced(data.cost_price_synced);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, [menuItemId]);

    const usedIds = new Set(lines.map((l) => l.inventory_item_id));
    const availableToAdd = inventoryItems.filter((i) => !usedIds.has(i.id));

    const addLine = () => {
        if (availableToAdd.length === 0) return;
        setLines([...lines, {
            inventory_item_id: availableToAdd[0].id,
            quantity_per_serving: "",
            is_critical: true,
        }]);
    };

    const updateLine = (idx: number, patch: Partial<RecipeLine>) => {
        setLines(lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
    };

    const removeLine = (idx: number) => {
        setLines(lines.filter((_, i) => i !== idx));
    };

    const formatKES = (cents: number) => `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 2 })}`;

    const lineCost = (line: RecipeLine) => {
        const inv = inventoryItems.find((i) => i.id === line.inventory_item_id);
        const qty = parseFloat(line.quantity_per_serving) || 0;
        if (!inv) return 0;
        // cost_per_unit is whole KES on InventoryItem; convert to cents to match
        // MenuItem.cost_price's unit — see stock_ledger.py's unit-boundary note.
        return Math.round(qty * inv.cost_per_unit * 100);
    };

    const previewCost = lines.reduce((sum, l) => sum + lineCost(l), 0);

    const handleSave = async () => {
        setError("");
        for (const line of lines) {
            const qty = parseFloat(line.quantity_per_serving);
            if (!qty || qty <= 0) {
                const inv = inventoryItems.find((i) => i.id === line.inventory_item_id);
                setError(`Enter a quantity greater than 0 for ${inv?.item_name || "an ingredient"}`);
                return;
            }
        }
        setSaving(true);
        try {
            const res = await api.put(`/menu/${menuItemId}/recipe`, {
                ingredients: lines.map((l) => ({
                    inventory_item_id: l.inventory_item_id,
                    quantity_per_serving: parseFloat(l.quantity_per_serving),
                    is_critical: l.is_critical,
                })),
                sync_cost_price: true,
            });
            setDerivedCostPrice(res.data.derived_cost_price);
            setStoredCostPrice(res.data.stored_cost_price);
            setSynced(res.data.cost_price_synced);
            onSaved?.(res.data.derived_cost_price);
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Couldn't save the recipe. Try again.");
        }
        setSaving(false);
    };

    return (
        <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 bg-[#0f0f0f] border border-[#262626] rounded-xl overflow-hidden"
        >
            <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                <p className="text-xs font-semibold text-[#e5e5e5]">Recipe — {menuItemName}</p>
                <p className="text-[10px] text-[#525252]">What this dish is made of, per serving</p>
            </div>

            <div className="p-4 space-y-3">
                {loading ? (
                    <div className="h-16 bg-[#141414] rounded-lg animate-pulse" />
                ) : inventoryItems.length === 0 ? (
                    <p className="text-xs text-[#525252]">
                        Add stock items on the{" "}
                        <a href="/dashboard/inventory" className="text-[#d4a853] hover:underline">Stock page</a>{" "}
                        before building a recipe.
                    </p>
                ) : (
                    <>
                        {lines.length === 0 && (
                            <p className="text-xs text-[#525252]">
                                No recipe yet. This dish&apos;s cost stays whatever was typed in manually, and
                                selling it won&apos;t deduct any stock.
                            </p>
                        )}

                        <div className="space-y-2">
                            {lines.map((line, idx) => {
                                const inv = inventoryItems.find((i) => i.id === line.inventory_item_id);
                                const selectableForThisRow = inventoryItems.filter(
                                    (i) => i.id === line.inventory_item_id || !usedIds.has(i.id)
                                );
                                return (
                                    <div key={idx} className="flex items-center gap-2">
                                        <select
                                            value={line.inventory_item_id}
                                            onChange={(e) => updateLine(idx, { inventory_item_id: Number(e.target.value) })}
                                            className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] focus:border-[#d4a853]/50 focus:outline-none"
                                        >
                                            {selectableForThisRow.map((i) => (
                                                <option key={i.id} value={i.id}>{i.item_name}</option>
                                            ))}
                                        </select>
                                        <input
                                            type="number" step="any" placeholder="Qty"
                                            value={line.quantity_per_serving}
                                            onChange={(e) => updateLine(idx, { quantity_per_serving: e.target.value })}
                                            className="w-20 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none"
                                        />
                                        <span className="text-[10px] text-[#525252] w-10">{inv?.unit}</span>
                                        <label className="flex items-center gap-1 text-[10px] text-[#737373] whitespace-nowrap" title="Uncheck for a garnish — present in the recipe but the dish can still be made without it">
                                            <input
                                                type="checkbox"
                                                checked={line.is_critical}
                                                onChange={(e) => updateLine(idx, { is_critical: e.target.checked })}
                                                className="accent-[#d4a853]"
                                            />
                                            required
                                        </label>
                                        <span className="text-[10px] text-[#525252] w-16 text-right">
                                            {line.quantity_per_serving ? formatKES(lineCost(line)) : ""}
                                        </span>
                                        <button onClick={() => removeLine(idx)} className="text-[#525252] hover:text-[#ef4444] transition-colors">
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                );
                            })}
                        </div>

                        {availableToAdd.length > 0 && (
                            <button onClick={addLine}
                                className="flex items-center gap-1.5 text-xs text-[#d4a853] hover:text-[#e0b96a] transition-colors">
                                <Plus className="w-3.5 h-3.5" /> Add ingredient
                            </button>
                        )}

                        {error && (
                            <div className="flex items-center gap-2 text-xs text-[#ef4444] bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-lg px-3 py-2">
                                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                            </div>
                        )}

                        <div className="flex items-center justify-between pt-2 border-t border-[#1a1a1a]">
                            <div className="text-[10px] text-[#525252]">
                                {lines.length > 0 ? (
                                    <>
                                        Cost from recipe: <span className="text-[#e5e5e5] font-medium">{formatKES(previewCost)}</span>
                                        {!synced && derivedCostPrice !== null && (
                                            <span className="ml-2 text-[#eab308]">
                                                (saved menu price still uses {formatKES(storedCostPrice)})
                                            </span>
                                        )}
                                    </>
                                ) : (
                                    <>Current menu cost: <span className="text-[#e5e5e5]">{formatKES(storedCostPrice)}</span> (typed in manually)</>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <button onClick={onClose}
                                    className="text-xs text-[#737373] hover:text-[#e5e5e5] px-3 py-1.5 transition-colors">
                                    Close
                                </button>
                                <button onClick={handleSave} disabled={saving}
                                    className="flex items-center gap-1.5 bg-[#d4a853] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50 transition-colors">
                                    {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                                    Save recipe
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </motion.div>
    );
}
