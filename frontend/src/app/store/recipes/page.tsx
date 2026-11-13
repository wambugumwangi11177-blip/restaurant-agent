"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { RecipeDiagram } from "@/components/store/diagrams";
import { loadSetup, stepById, type SetupPayload } from "@/lib/storeSetup";

type Line = { id: number; ingredient_name: string; quantity: number; unit: string; yield_fraction: number };
type Dish = { id: number; name: string; lines: Line[] };

const UNITS = ["kg", "g", "litre", "ml", "piece", "bunch"];

export default function StoreRecipesPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [dishes, setDishes] = useState<Dish[]>([]);
  const [dishName, setDishName] = useState("");
  const [ingredientName, setIngredientName] = useState("");
  const [quantity, setQuantity] = useState("0.25");
  const [unit, setUnit] = useState("kg");
  const [yieldFraction, setYieldFraction] = useState("1");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    const [nextSetup, recipeResponse] = await Promise.all([
      loadSetup(),
      api.get("/api/v1/store/recipes").catch(() => null),
    ]);
    setSetup(nextSetup);
    if (recipeResponse) setDishes(recipeResponse.data.dishes ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Recipes could not be loaded."));
  }, []);

  const account = stepById(setup, "account");
  const recipes = stepById(setup, "recipes");
  if (setup && account?.state !== "done") {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Recipes are locked</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          Unlocks after you change the password you were given and set your own 4-digit PIN.
        </p>
        <Link href="/store/account" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">
          Open account
        </Link>
      </section>
    );
  }

  async function saveLine(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      const response = await api.post("/api/v1/store/recipes", {
        dish_name: dishName,
        ingredient_name: ingredientName,
        quantity: Number(quantity),
        unit,
        yield_fraction: Number(yieldFraction),
      });
      setDishes(response.data.dishes ?? []);
      setIngredientName("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That recipe line was not saved.");
    } finally {
      setSaving(false);
    }
  }

  async function finishStep() {
    setError("");
    try {
      const response = await api.post("/api/v1/staff-setup/recipes");
      setSetup(response.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The recipe step is not finished yet.");
    }
  }

  const lineCount = dishes.reduce((sum, dish) => sum + dish.lines.length, 0);

  return (
    <div className="space-y-4">
      <section className="owner-glass-panel rounded-3xl p-4">
        <RecipeDiagram />
        <p className="text-sm leading-6 text-zinc-300">
          Write what the chefs cook. Quantity and unit are what goes into one plate. Yield is how much of the raw ingredient is left after prep. 1 means nothing is lost.
        </p>
      </section>
      <form onSubmit={saveLine} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <label className="block text-sm">
          Dish
          <input required value={dishName} onChange={(event) => setDishName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <label className="block text-sm">
          Ingredient
          <input required value={ingredientName} onChange={(event) => setIngredientName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Quantity
            <input required inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">
            Unit
            <select value={unit} onChange={(event) => setUnit(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
              {UNITS.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
        </div>
        <label className="block text-sm">
          Yield (0 to 1)
          <input required inputMode="decimal" min="0.01" max="1" step="0.01" value={yieldFraction} onChange={(event) => setYieldFraction(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" disabled={saving} className="min-h-11 w-full rounded-full bg-white font-semibold text-black disabled:opacity-60">
          {saving ? "Saving…" : "Save recipe line"}
        </button>
      </form>
      <section className="space-y-3">
        {dishes.map((dish) => (
          <article key={dish.id} className="owner-glass-panel rounded-3xl p-4">
            <h2 className="font-semibold">{dish.name}</h2>
            <ul className="mt-2 space-y-1 text-sm text-zinc-300">
              {dish.lines.map((line) => (
                <li key={line.id}>
                  {line.quantity} {line.unit} {line.ingredient_name} · yield {line.yield_fraction}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>
      {recipes?.state !== "done" && (
        <button
          type="button"
          disabled={lineCount < 1}
          onClick={finishStep}
          className="min-h-11 w-full rounded-full border border-white/30 font-semibold disabled:opacity-40"
        >
          These recipes are in
        </button>
      )}
      {recipes?.state === "done" && (
        <p className="text-sm text-zinc-300">Recipes are in. Stock counts are unlocked.</p>
      )}
    </div>
  );
}
