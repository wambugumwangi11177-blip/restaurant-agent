"""
backend/demo/catalog.py — what the demo restaurant sells, buys and employs (docs/v2/SPEC.md §6).

Pure data and pure functions: no database, no randomness. Money is integer cents. A dish's cost price is the sum
of its recipe (quantity × ingredient cost), so the menu, the recipes and the stock engine always agree — the same
rule the owner's real restaurant should be following.

The spec fixes a handful of dishes exactly (§6): Quarter chicken KES 400 / cost 260, Chips 300 / 90, Burger 600 / 280,
Fish fillet 650 / 260, Pilau 350. They are built from ingredient prices and quantities below so those numbers fall out
of the recipes rather than being typed in; `tests/test_demo_generator.py` pins them.

Names are plain Kenyan restaurant fare; suppliers are generic descriptions rather than real businesses (the one
exception is Kenchic, which figure 6.1 names for the short-delivery scenario P13). No real person or number appears.
"""
from __future__ import annotations

from dataclasses import dataclass, field

KES = 100  # cents per shilling

# ── ingredients ──────────────────────────────────────────────────────────────
# key: (display name, unit, cost per unit in cents, supplier key, shelf life in days, spoils)
# `spoils` ingredients get a small weekly waste movement; dry goods and bottles do not.


@dataclass(frozen=True)
class Ingredient:
    key: str
    name: str
    unit: str
    cost_cents: int
    supplier: str
    shelf_days: int
    spoils: bool
    pack: float = 1.0          # deliveries come in whole packs of this size


INGREDIENTS: tuple[Ingredient, ...] = (
    Ingredient("chicken", "Chicken", "kg", 48_000, "kenchic", 4, True, 5.0),
    Ingredient("beef", "Beef", "kg", 80_000, "butchery", 5, True, 5.0),
    Ingredient("beef_mince", "Beef mince", "kg", 80_000, "butchery", 4, True, 5.0),
    Ingredient("goat", "Goat meat", "kg", 90_000, "butchery", 5, True, 5.0),
    Ingredient("tilapia", "Tilapia", "kg", 60_000, "fish", 3, True, 5.0),
    Ingredient("eggs", "Eggs", "piece", 2_500, "produce", 14, True, 30.0),
    Ingredient("potatoes", "Potatoes", "kg", 10_000, "produce", 14, True, 25.0),
    Ingredient("tomatoes", "Tomatoes", "kg", 12_000, "produce", 6, True, 10.0),
    Ingredient("onions", "Onions", "kg", 10_000, "produce", 21, True, 10.0),
    Ingredient("kale", "Sukuma wiki (kale)", "kg", 6_000, "produce", 4, True, 5.0),
    Ingredient("carrots", "Carrots", "kg", 9_000, "produce", 14, True, 5.0),
    Ingredient("lettuce", "Lettuce", "kg", 6_000, "produce", 4, True, 3.0),
    Ingredient("lemons", "Lemons", "piece", 1_000, "produce", 14, True, 20.0),
    Ingredient("avocado", "Avocado", "piece", 3_000, "produce", 5, True, 10.0),
    Ingredient("mangoes", "Mangoes", "kg", 15_000, "produce", 5, True, 5.0),
    Ingredient("passion", "Passion fruit", "kg", 30_000, "produce", 7, True, 3.0),
    Ingredient("pineapple", "Pineapple", "piece", 15_000, "produce", 6, True, 4.0),
    Ingredient("oranges", "Oranges", "kg", 12_000, "produce", 10, True, 5.0),
    Ingredient("watermelon", "Watermelon", "kg", 6_000, "produce", 7, True, 10.0),
    Ingredient("rice", "Rice", "kg", 18_000, "drygoods", 365, False, 25.0),
    Ingredient("pasta", "Pasta", "kg", 25_000, "drygoods", 365, False, 10.0),
    Ingredient("maize_flour", "Maize flour", "kg", 14_000, "drygoods", 180, False, 24.0),
    Ingredient("wheat_flour", "Wheat flour", "kg", 11_000, "drygoods", 180, False, 24.0),
    Ingredient("beans", "Beans", "kg", 20_000, "drygoods", 365, False, 10.0),
    Ingredient("sugar", "Sugar", "kg", 16_000, "drygoods", 365, False, 10.0),
    Ingredient("tea", "Tea leaves", "kg", 40_000, "drygoods", 365, False, 1.0),
    Ingredient("spices", "Spice mix", "kg", 40_000, "drygoods", 365, False, 1.0),
    Ingredient("oil", "Cooking oil", "L", 20_000, "drygoods", 365, False, 10.0),
    Ingredient("milk", "Milk", "L", 6_500, "dairy", 5, True, 20.0),
    Ingredient("buns", "Burger buns", "piece", 4_000, "bakery", 4, True, 24.0),
    Ingredient("cheese", "Cheese slices", "piece", 3_000, "bakery", 30, False, 50.0),
    Ingredient("soda", "Soda (300 ml)", "bottle", 4_500, "beverages", 365, False, 24.0),
    Ingredient("water", "Drinking water (500 ml)", "bottle", 2_000, "beverages", 365, False, 24.0),
    Ingredient("beer", "Beer (500 ml)", "bottle", 12_000, "beverages", 365, False, 24.0),
    Ingredient("whisky", "Whisky (750 ml bottle)", "bottle", 250_000, "beverages", 365, False, 6.0),
)
ING = {i.key: i for i in INGREDIENTS}

# ── menu ─────────────────────────────────────────────────────────────────────
# name, category, price in cents, station, prep minutes, popularity weight, recipe {ingredient: quantity per serving}


@dataclass(frozen=True)
class Dish:
    name: str
    category: str
    price_cents: int
    station: str
    prep_minutes: float
    weight: float                    # relative popularity — drives how often it is ordered
    recipe: dict = field(default_factory=dict)
    drink: bool = False

    @property
    def cost_cents(self) -> int:
        return round(sum(qty * ING[k].cost_cents for k, qty in self.recipe.items()))


MENU: tuple[Dish, ...] = (
    # grill
    Dish("Quarter chicken", "Mains", 40_000, "grill", 18, 6.5, {"chicken": 0.5, "oil": 0.1}),
    Dish("Nyama choma (goat)", "Mains", 120_000, "grill", 22, 6.5,
         {"goat": 0.35, "tomatoes": 0.1, "onions": 0.08, "maize_flour": 0.15, "spices": 0.01}),
    Dish("Burger", "Mains", 60_000, "grill", 12, 3.5,
         {"beef_mince": 0.22, "buns": 1, "cheese": 1, "tomatoes": 0.15, "onions": 0.1, "lettuce": 0.1}),
    Dish("Chicken burger", "Mains", 65_000, "grill", 12, 3.0,
         {"chicken": 0.2, "buns": 1, "cheese": 1, "lettuce": 0.1, "tomatoes": 0.15}),
    # fryer
    Dish("Chips", "Sides", 30_000, "fryer", 9, 10.0, {"potatoes": 0.4, "oil": 0.25}),
    Dish("Fish fillet", "Mains", 65_000, "fryer", 15, 1.8,
         {"tilapia": 0.3, "oil": 0.15, "lemons": 1, "maize_flour": 0.15, "tomatoes": 0.1, "onions": 0.07}),
    Dish("Chicken wings", "Mains", 60_000, "fryer", 14, 3.0, {"chicken": 0.4, "oil": 0.1}),
    Dish("Samosa (2)", "Snacks", 20_000, "fryer", 6, 5.0, {"wheat_flour": 0.06, "beef": 0.05, "oil": 0.05, "onions": 0.03}),
    Dish("Mandazi (3)", "Snacks", 12_000, "fryer", 5, 4.0, {"wheat_flour": 0.1, "sugar": 0.02, "oil": 0.05}),
    # main kitchen
    Dish("Pilau", "Mains", 35_000, "main", 14, 8.0,
         {"rice": 0.15, "beef": 0.1, "spices": 0.01, "onions": 0.05, "oil": 0.03}),
    Dish("Beef stew", "Mains", 65_000, "main", 16, 4.0,
         {"beef": 0.22, "onions": 0.05, "tomatoes": 0.1, "oil": 0.03, "maize_flour": 0.12}),
    Dish("Fried rice", "Mains", 45_000, "main", 13, 5.0,
         {"rice": 0.15, "eggs": 1, "carrots": 0.05, "oil": 0.03, "chicken": 0.08}),
    Dish("Ugali sukuma", "Mains", 30_000, "main", 10, 6.0,
         {"maize_flour": 0.2, "kale": 0.15, "oil": 0.02, "onions": 0.03}),
    Dish("Chapati beans", "Mains", 30_000, "main", 10, 4.0,
         {"wheat_flour": 0.1, "beans": 0.15, "oil": 0.04, "onions": 0.03}),
    Dish("Omelette", "Breakfast", 35_000, "main", 8, 3.0, {"eggs": 3, "onions": 0.03, "tomatoes": 0.05, "oil": 0.02}),
    Dish("Spaghetti bolognese", "Mains", 38_000, "main", 13, 1.2,
         {"pasta": 0.15, "beef_mince": 0.1, "tomatoes": 0.1, "onions": 0.05, "oil": 0.02}),
    # salad
    Dish("Garden salad", "Sides", 35_000, "salad", 5, 1.5,
         {"lettuce": 0.15, "tomatoes": 0.15, "carrots": 0.05, "avocado": 0.5}),
    Dish("Kachumbari", "Sides", 12_000, "salad", 3, 3.0, {"tomatoes": 0.15, "onions": 0.08}),
    # drinks
    Dish("Chai (milk tea)", "Drinks", 10_000, "drinks", 3, 9.0,
         {"tea": 0.005, "milk": 0.15, "sugar": 0.01}, drink=True),
    Dish("Mango juice", "Drinks", 30_000, "drinks", 4, 4.0, {"mangoes": 0.35, "sugar": 0.02}, drink=True),
    Dish("Passion juice", "Drinks", 30_000, "drinks", 4, 3.0, {"passion": 0.3, "sugar": 0.02}, drink=True),
    Dish("Pineapple juice", "Drinks", 30_000, "drinks", 4, 2.5, {"pineapple": 0.25, "sugar": 0.02}, drink=True),
    Dish("Orange juice", "Drinks", 30_000, "drinks", 4, 2.5, {"oranges": 0.5, "sugar": 0.02}, drink=True),
    Dish("Watermelon juice", "Drinks", 25_000, "drinks", 4, 2.5, {"watermelon": 0.5, "sugar": 0.02}, drink=True),
    Dish("Soda", "Drinks", 12_000, "drinks", 1, 8.0, {"soda": 1}, drink=True),
    Dish("Water 500 ml", "Drinks", 12_000, "drinks", 1, 4.0, {"water": 1}, drink=True),
    Dish("Beer", "Drinks", 35_000, "drinks", 1, 6.0, {"beer": 1}, drink=True),
    Dish("Whisky (shot)", "Drinks", 40_000, "drinks", 1, 2.0, {"whisky": 0.04}, drink=True),
)
DISH = {d.name: d for d in MENU}


def average_order_cents() -> float:
    """Expected value of one order given the dish weights and the basket-size distribution below."""
    mean_price = sum(d.price_cents * d.weight for d in MENU) / sum(d.weight for d in MENU)
    return mean_price * BASKET_MEAN_LINES * LINE_MEAN_QTY


BASKET_SIZES = (1, 2, 3, 4)
BASKET_WEIGHTS = (26, 38, 24, 12)
BASKET_MEAN_LINES = sum(s * w for s, w in zip(BASKET_SIZES, BASKET_WEIGHTS)) / sum(BASKET_WEIGHTS)
LINE_QTYS = (1, 2, 3)
LINE_QTY_WEIGHTS = (85, 13, 2)
LINE_MEAN_QTY = sum(q * w for q, w in zip(LINE_QTYS, LINE_QTY_WEIGHTS)) / sum(LINE_QTY_WEIGHTS)

# ── suppliers ────────────────────────────────────────────────────────────────
# key: (name, contact, promised lead days, on-time rate)
SUPPLIERS: dict[str, dict] = {
    "kenchic": {"name": "Kenchic", "lead_days": 1.0, "on_time": 0.92},
    "butchery": {"name": "Rift Valley Butchery", "lead_days": 1.0, "on_time": 0.94},
    "fish": {"name": "Lakeside Fish Traders", "lead_days": 1.0, "on_time": 0.88},
    "produce": {"name": "Wangari Fresh Produce", "lead_days": 1.0, "on_time": 0.90},
    "drygoods": {"name": "Mama Pima Dry Goods", "lead_days": 2.0, "on_time": 0.97},
    "dairy": {"name": "Highland Dairy Depot", "lead_days": 1.0, "on_time": 0.96},
    "bakery": {"name": "Corner Bakery & Cheese", "lead_days": 1.0, "on_time": 0.95},
    "beverages": {"name": "Crown Beverages Distributors", "lead_days": 2.0, "on_time": 0.98},
}

# ── branches ─────────────────────────────────────────────────────────────────
# `scale` multiplies the weekly sales target; `waste` is the baseline kitchen waste share; `cost_factor` multiplies the
# ingredient prices a branch pays (1.00 everywhere in the baseline; S2.2 plants figure 6.1's branch comparison P14 by
# raising Kasarani's).
BRANCHES: tuple[dict, ...] = (
    {"key": "westlands", "name": "Demo Restaurant", "label": "Westlands", "address": "Westlands, Nairobi",
     "scale": 1.00, "tables": 14, "waste": 0.012, "cost_factor": 1.00, "lat": -1.2673, "lng": 36.8103},
    {"key": "kasarani", "name": "Demo Restaurant – Kasarani", "label": "Kasarani", "address": "Kasarani, Nairobi",
     "scale": 0.93, "tables": 12, "waste": 0.016, "cost_factor": 1.00, "lat": -1.2210, "lng": 36.8990},
)
WEEKLY_SALES_TARGET_CENTS = 10_000_000          # KES 100,000 per branch per week

# Share of a week's orders by weekday (Mon..Sun); mean is 1.0 so the weekly total is the target.
WEEKDAY_FACTORS = (0.78, 0.80, 0.90, 1.00, 1.25, 1.35, 0.92)

# daypart (EAT hour range [start, end)), share of the day's orders
DAYPARTS = (("breakfast", 8, 12, 0.11), ("lunch", 12, 15, 0.37), ("afternoon", 15, 18, 0.14),
            ("dinner", 18, 22, 0.34), ("late", 22, 23, 0.04))

# ── staff ────────────────────────────────────────────────────────────────────
# title, hourly rate (cents), shifts per week, station / section
STAFF: tuple[tuple[str, str, int, int], ...] = (
    ("Wanjiru", "Manager", 16_000, 5),
    ("Otieno", "Head chef", 14_000, 5),
    ("Kamau", "Cook", 10_000, 5),
    ("Achieng", "Cook", 9_500, 5),
    ("Mwende", "Waiter", 8_000, 5),
    ("Njoroge", "Waiter", 7_500, 5),
    ("Chebet", "Cashier", 8_500, 5),
    ("Barasa", "Storekeeper", 8_500, 5),
)

# first names for the regular-guest pool (fictional guests; numbers are deliberately not dialable)
GUEST_NAMES = ("Amani", "Baraka", "Chausiku", "Dalila", "Emali", "Faraja", "Gathoni", "Halima", "Imani", "Jabali",
               "Kendi", "Lulu", "Mosi", "Nyambura", "Omari", "Pendo", "Rehema", "Sade", "Tumaini", "Wambui")
