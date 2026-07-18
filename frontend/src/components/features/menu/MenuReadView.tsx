"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { UtensilsCrossed, ChefHat, ChevronDown, ChevronUp } from "lucide-react";

interface MenuItem {
    id: number;
    name: string;
    description: string;
    price: number;
    category: string;
    is_available: boolean;
}

/**
 * Read-only menu + recipe view — for tiers with `menu` = R (directive 015:
 * Supervisor, Kitchen, Waiter). Deliberately not the full MenuEditor (CRUD +
 * AI menu engineering, Owner/Manager only): a Kitchen cook needs to see
 * what's in a dish, not edit it or read margin analytics.
 */
export default function MenuReadView() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [openId, setOpenId] = useState<number | null>(null);
    const [ingredientsByItem, setIngredientsByItem] = useState<Record<number, any[]>>({});

    useEffect(() => {
        api.get("/menu/").then((res) => setItems(res.data || [])).finally(() => setLoading(false));
    }, []);

    const toggle = async (itemId: number) => {
        if (openId === itemId) {
            setOpenId(null);
            return;
        }
        setOpenId(itemId);
        if (!ingredientsByItem[itemId]) {
            try {
                const res = await api.get(`/menu/${itemId}/ingredients`);
                setIngredientsByItem((prev) => ({ ...prev, [itemId]: res.data }));
            } catch {
                setIngredientsByItem((prev) => ({ ...prev, [itemId]: [] }));
            }
        }
    };

    if (loading) {
        return (
            <div className="space-y-2">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Menu</h1>
                <p className="text-sm text-[#525252] mt-0.5">{items.length} item{items.length !== 1 ? "s" : ""}</p>
            </div>

            <div className="bg-[#141414] border border-[#262626] rounded-xl divide-y divide-[#1a1a1a]">
                {items.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                        <UtensilsCrossed className="w-8 h-8 text-[#333] mx-auto mb-3" />
                        <p className="text-sm text-[#525252]">No menu items yet</p>
                    </div>
                ) : (
                    items.map((item) => {
                        const ingredients = ingredientsByItem[item.id];
                        const isOpen = openId === item.id;
                        return (
                            <div key={item.id}>
                                <button
                                    onClick={() => toggle(item.id)}
                                    className="w-full px-4 py-3 flex items-center justify-between hover:bg-[#1a1a1a] transition-colors text-left"
                                >
                                    <div className="flex items-center gap-2">
                                        {!item.is_available && (
                                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#ef4444]/10 text-[#ef4444] uppercase">86'd</span>
                                        )}
                                        <div>
                                            <p className="text-sm text-[#e5e5e5]">{item.name}</p>
                                            <p className="text-xs text-[#525252]">{item.category}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-sm font-medium text-[var(--accent)]">
                                            KES {(item.price / 100).toLocaleString("en-KE")}
                                        </span>
                                        {isOpen ? <ChevronUp className="w-4 h-4 text-[#525252]" /> : <ChevronDown className="w-4 h-4 text-[#525252]" />}
                                    </div>
                                </button>
                                {isOpen && (
                                    <div className="px-4 pb-3">
                                        {item.description && (
                                            <p className="text-xs text-[#737373] mb-2">{item.description}</p>
                                        )}
                                        <div className="flex items-center gap-1.5 mb-1.5">
                                            <ChefHat className="w-3 h-3 text-[#525252]" />
                                            <span className="text-[10px] text-[#525252] uppercase tracking-wider">Recipe</span>
                                        </div>
                                        {!ingredients ? (
                                            <p className="text-xs text-[#525252]">Loading…</p>
                                        ) : ingredients.length === 0 ? (
                                            <p className="text-xs text-[#525252]">No recipe set for this item.</p>
                                        ) : (
                                            <ul className="space-y-0.5">
                                                {ingredients.map((ing: any) => (
                                                    <li key={ing.id} className="text-xs text-[#e5e5e5]">
                                                        {ing.quantity_per_serving} {ing.unit || ""} {ing.inventory_item_name || `Item #${ing.inventory_item_id}`}
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}
