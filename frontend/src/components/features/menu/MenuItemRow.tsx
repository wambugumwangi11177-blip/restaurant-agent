"use client";

import { motion } from "framer-motion";
import { ChefHat, Trash2, Pencil } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { MenuItem, MenuAiItem, RecipeIngredient, InventoryPickItem } from "./types";

interface EditForm {
    name: string;
    price: string;
    category: string;
    description: string;
    avg_prep_minutes: string;
    image_url: string;
}

interface MenuItemRowProps {
    item: MenuItem;
    idx: number;
    aiItem: MenuAiItem;
    classColor: (c: string) => string;
    classLabel: (c: string) => string;
    editingId: number | null;
    openEdit: (item: MenuItem) => void;
    editForm: EditForm;
    setEditForm: (f: EditForm) => void;
    setEditingId: (id: number | null) => void;
    handleSaveEdit: (itemId: number) => void;
    editSaving: boolean;
    recipeOpenId: number | null;
    toggleRecipe: (itemId: number) => void;
    ingredients: RecipeIngredient[];
    inventoryItems: InventoryPickItem[];
    newIngredientId: string;
    setNewIngredientId: (v: string) => void;
    newIngredientQty: string;
    setNewIngredientQty: (v: string) => void;
    handleAddIngredient: (itemId: number) => void;
    handleRemoveIngredient: (itemId: number, ingredientId: number) => void;
    recipeSaving: boolean;
    toggleAvailability: (item: MenuItem) => void;
}

/**
 * One menu item row — availability toggle, edit form, and recipe/ingredient
 * editor. Extracted from MenuEditor unmodified; open/edit state stays lifted
 * in the parent so only one item's edit form or recipe panel is open at a
 * time, matching the original behavior.
 */
export default function MenuItemRow({
    item, idx, aiItem, classColor, classLabel,
    editingId, openEdit, editForm, setEditForm, setEditingId, handleSaveEdit, editSaving,
    recipeOpenId, toggleRecipe, ingredients, inventoryItems,
    newIngredientId, setNewIngredientId, newIngredientQty, setNewIngredientQty,
    handleAddIngredient, handleRemoveIngredient, recipeSaving,
    toggleAvailability,
}: MenuItemRowProps) {
    const recipeOpen = recipeOpenId === item.id;
    const hasRecipe = ingredients.length > 0;

    return (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            transition={{ delay: idx * 0.03 }}
            className="bg-surface border border-border rounded-xl overflow-hidden hover:border-[#333] transition-colors">
            <div className="px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    {aiItem && (
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${classColor(aiItem.classification)}`}>
                            {classLabel(aiItem.classification)}
                        </span>
                    )}
                    <div>
                        <p className={`text-sm font-medium ${item.is_available ? "text-text" : "text-text-dim line-through"}`}>
                            {item.name}
                        </p>
                        {item.description && (
                            <p className="text-xs text-text-dim mt-0.5">{item.description}</p>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {aiItem?.margin_pct !== undefined && (
                        <span className={`text-[10px] ${aiItem.margin_pct >= 60 ? "text-success" : aiItem.margin_pct >= 30 ? "text-text-muted" : "text-danger"
                            }`}>{aiItem.margin_pct.toFixed(0)}% profit</span>
                    )}
                    <span className="text-sm font-semibold text-accent">
                        KES {(item.price / 100).toLocaleString()}
                    </span>
                    <button onClick={() => openEdit(item)}
                        title="Edit — name, price, category, prep time, photo"
                        className={`text-[10px] px-2 py-1 rounded flex items-center gap-1 transition-all ${editingId === item.id ? "bg-accent/10 text-accent" : "bg-surface-hover text-text-muted hover:text-accent"}`}>
                        <Pencil className="w-3 h-3" />
                        Edit
                    </button>
                    <button onClick={() => toggleRecipe(item.id)}
                        title="Recipe — what this dish is made of"
                        className={`text-[10px] px-2 py-1 rounded flex items-center gap-1 transition-all ${recipeOpen ? "bg-accent/10 text-accent" : "bg-surface-hover text-text-muted hover:text-accent"}`}>
                        <ChefHat className="w-3 h-3" />
                        Recipe
                    </button>
                    <button onClick={() => toggleAvailability(item)}
                        role="switch"
                        aria-checked={item.is_available}
                        aria-label={`Mark ${item.name} as ${item.is_available ? "unavailable" : "available"}`}
                        className={`w-8 h-5 rounded-full relative transition-colors ${item.is_available ? "bg-success" : "bg-[#333]"}`}>
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${item.is_available ? "left-3.5" : "left-0.5"}`} />
                    </button>
                </div>
            </div>

            {editingId === item.id && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                    className="border-t border-surface-hover px-4 py-3 bg-[#0f0f0f] space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                        <FormField
                            label="Name"
                            placeholder="Name" value={editForm.name}
                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                            className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        <FormField
                            label="Price (KES)"
                            placeholder="Price (KES)" value={editForm.price} type="number"
                            onChange={(e) => setEditForm({ ...editForm, price: e.target.value })}
                            className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        <FormField
                            label="Category"
                            placeholder="Category" value={editForm.category}
                            onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                            className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        <FormField
                            label="Prep time (minutes)"
                            placeholder="Prep time (minutes)" value={editForm.avg_prep_minutes} type="number"
                            onChange={(e) => setEditForm({ ...editForm, avg_prep_minutes: e.target.value })}
                            className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        <div className="col-span-2">
                            <FormField
                                label="Description"
                                placeholder="Description" value={editForm.description}
                                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                                className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        </div>
                        <div className="col-span-2">
                            <FormField
                                label="Photo URL"
                                placeholder="Photo URL" value={editForm.image_url}
                                onChange={(e) => setEditForm({ ...editForm, image_url: e.target.value })}
                                className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none w-full" />
                        </div>
                    </div>
                    <div className="flex justify-end gap-2 pt-1">
                        <button onClick={() => setEditingId(null)}
                            className="text-xs px-3 py-1.5 rounded-lg text-text-muted hover:text-text transition-colors">
                            Cancel
                        </button>
                        <button onClick={() => handleSaveEdit(item.id)} disabled={!editForm.name || !editForm.price || editSaving}
                            className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                            {editSaving ? "Saving..." : "Save"}
                        </button>
                    </div>
                </motion.div>
            )}

            {recipeOpen && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                    className="border-t border-surface-hover px-4 py-3 bg-[#0f0f0f] space-y-2">
                    {!hasRecipe && (
                        <p className="text-[11px] text-warning">
                            No recipe set — this dish&apos;s sales won&apos;t deduct stock until you add ingredients.
                        </p>
                    )}
                    {ingredients.map((ing) => (
                        <div key={ing.id} className="flex items-center justify-between text-xs">
                            <span className="text-text">{ing.item_name}</span>
                            <div className="flex items-center gap-2">
                                <span className="text-text-muted">{ing.quantity_per_serving} {ing.unit} / serving</span>
                                <button onClick={() => handleRemoveIngredient(item.id, ing.id)}
                                    aria-label={`Remove ${ing.item_name}`}
                                    className="text-text-dim hover:text-danger transition-colors">
                                    <Trash2 className="w-3 h-3" />
                                </button>
                            </div>
                        </div>
                    ))}
                    <div className="flex gap-2 items-center pt-2">
                        <div className="flex-1 flex flex-col gap-1">
                            <label htmlFor={`ingredient-select-${item.id}`} className="sr-only">Add ingredient</label>
                            <select id={`ingredient-select-${item.id}`} value={newIngredientId} onChange={(e) => setNewIngredientId(e.target.value)}
                                className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                <option value="">Add ingredient…</option>
                                {inventoryItems.map((inv) => (
                                    <option key={inv.id} value={inv.id}>{inv.item_name} ({inv.unit})</option>
                                ))}
                            </select>
                        </div>
                        <FormField
                            label="Qty / serving"
                            srOnlyLabel
                            placeholder="Qty / serving" value={newIngredientQty}
                            onChange={(e) => setNewIngredientQty(e.target.value)} type="number"
                            className="w-28 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                        <button onClick={() => handleAddIngredient(item.id)} disabled={!newIngredientId || !newIngredientQty || recipeSaving}
                            className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                            {recipeSaving ? "..." : "Add"}
                        </button>
                    </div>
                </motion.div>
            )}
        </motion.div>
    );
}
