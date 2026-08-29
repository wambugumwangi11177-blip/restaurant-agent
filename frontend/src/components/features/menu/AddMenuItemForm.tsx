"use client";

import { useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { ToastType } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";

interface AddMenuItemFormProps {
    onAdded: () => void;
    onClose: () => void;
    showToast: (message: string, type?: ToastType) => void;
}

/**
 * New menu item form, extracted from MenuEditor unmodified aside from
 * owning its own name/price/category/description/saving state.
 */
export default function AddMenuItemForm({ onAdded, onClose, showToast }: AddMenuItemFormProps) {
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({ name: "", price: "", category: "", description: "" });

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
            onClose();
            onAdded();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add item"), "error");
        }
        setSaving(false);
    };

    return (
        <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
            onSubmit={handleAdd}
            className="bg-surface border border-border rounded-xl p-5 space-y-3">
            <p className="text-sm text-text font-medium">New Menu Item</p>
            <div className="grid grid-cols-2 gap-3">
                <FormField
                    label="Name"
                    type="text" placeholder="Name (e.g. Nyama Choma)" value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="px-3 py-2 rounded-lg bg-bg border border-border focus:border-accent outline-none text-sm text-text placeholder-text-dim w-full" required />
                <FormField
                    label="Price"
                    type="number" placeholder="Price in KES" value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })}
                    className="px-3 py-2 rounded-lg bg-bg border border-border focus:border-accent outline-none text-sm text-text placeholder-text-dim w-full" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
                <FormField
                    label="Category"
                    type="text" placeholder="Category (e.g. Mains, Drinks)" value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="px-3 py-2 rounded-lg bg-bg border border-border focus:border-accent outline-none text-sm text-text placeholder-text-dim w-full" />
                <FormField
                    label="Description"
                    type="text" placeholder="Short description" value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="px-3 py-2 rounded-lg bg-bg border border-border focus:border-accent outline-none text-sm text-text placeholder-text-dim w-full" />
            </div>
            <button type="submit" disabled={saving}
                className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-bg text-sm font-medium disabled:opacity-50 flex items-center gap-2 transition-colors">
                {saving && <Loader2 className="w-3 h-3 animate-spin" />} Add to Menu
            </button>
        </motion.form>
    );
}
