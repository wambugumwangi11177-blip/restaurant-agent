"""
backend/seed_recipes.py — link menu items to ingredients (menu_ingredients)
──────────────────────────────────────────────────────────────────────────────
The knowledge-graph cascade ("if Chicken runs out, which dishes are affected,
and how much revenue is at risk?") and order-time ingredient deduction both
read menu_ingredients — which was completely empty, so /ai/graph/impact
returned "0 affected dishes" for every ingredient despite a 208-node graph.

The Menu UI already has per-item ingredient management (the "input place" for
this data); this script backfills sensible defaults from item names so the
graph works immediately. Owners can then refine quantities per item in the UI.

Usage:
    venv/bin/python seed_recipes.py                 # current DATABASE_URL
    venv/bin/python seed_recipes.py --remote        # also REMOTE_DATABASE_URL (Neon)

Idempotent: only inserts links that don't already exist, never touches
existing rows.
"""

import re
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) if (os := __import__("os")) else None

# (item-name regex, ingredient name, quantity per serving in the ingredient's
#  unit, is_critical). First matching rule per (item, ingredient) wins; an item
# accumulates one row per distinct ingredient across all matching rules.
RULES = [
    (r"espresso|americano", "Coffee Beans", 0.02, True),
    (r"cappuccino|latte|mocha|flat white|macchiato|affagato|coffee", "Coffee Beans", 0.03, True),
    (r"cappuccino|latte|mocha|flat white|macchiato|matcha|chai|tea|dawa|hot chocolate|shake|smoothie", "Milk", 0.2, False),
    (r"smoothie|shake|lemonade|mojito|juice", "Sugar", 0.02, False),
    (r"mango", "Mango", 0.15, True),
    (r"passion", "Passion Fruit", 0.12, True),
    (r"dawa|turmeric|ginger|hibiscus", "Ginger", 0.01, False),
    (r"soda", "Soda (assorted)", 1.0, True),
    (r"croissant|croffle|roll|bun|bread|toast|biscoff", "Wheat Flour", 0.08, True),
    (r"croissant|croffle|cake|cinnamon|pancake|crepe|waffle|malawa|pie|samosa|bhajia", "Wheat Flour", 0.1, True),
    (r"croissant|cake|cinnamon|pancake|crepe|waffle|malawa", "Butter", 0.02, False),
    (r"cake|pancake|crepe|waffle|shakshuka|ranchers|highwayman|breakfast|crack wrap", "Eggs", 0.12, True),
    (r"cake|porridge|granola", "Sugar", 0.03, False),
    (r"chicken", "Chicken", 0.2, True),
    (r"beef|suqaar|otkac|samosa|pie", "Beef", 0.15, False),
    (r"goat|suqaar|otkac", "Goat Meat", 0.15, True),
    (r"liver|suqaar|otkac|stir|curry|shakshuka|soup", "Onions", 0.05, False),
    (r"salad|shakshuka|soup|sandwich|bhajia|suqaar", "Tomatoes", 0.06, False),
    (r"salad", "Lettuce", 0.05, True),
    (r"salad|pepper|stir", "Bell Peppers", 0.04, False),
    (r"salad|stir|curry", "Garlic", 0.01, False),
    (r"fish|tilapia|seafood", "Fish (Tilapia)", 0.2, True),
    (r"prawn|shrimp|seafood", "Prawns", 0.15, True),
    (r"bacon|breakfast|ranchers|highwayman", "Bacon", 0.05, False),
    (r"sausage|breakfast|ranchers|highwayman", "Beef Sausages", 0.06, False),
    (r"potato|bhajia|breakfast|ranchers|highwayman|platter", "Potatoes", 0.15, False),
    (r"rice|biryani|pilau", "Rice (Basmati)", 0.15, True),
    (r"pasta|carbonara|lasagna", "Pasta", 0.12, True),
    (r"cheese|cheesecake|burger|sandwich", "Cheese", 0.04, False),
    (r"coconut", "Coconut Milk", 0.1, True),
    (r"toast|sandwich|burger|breakfast", "Bread", 0.08, False),
]


def seed(db) -> int:
    import models
    added = 0
    restaurants = db.query(models.Restaurant).all()
    for rest in restaurants:
        inv = {i.item_name: i for i in db.query(models.InventoryItem)
               .filter(models.InventoryItem.restaurant_id == rest.id).all()}
        items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == rest.id).all()
        existing = {
            (mi.menu_item_id, mi.inventory_item_id)
            for mi in db.query(models.MenuIngredient).all()
        }
        for item in items:
            name = (item.name or "").lower()
            for pattern, ing_name, qty, critical in RULES:
                ing = inv.get(ing_name)
                if not ing or not re.search(pattern, name):
                    continue
                if (item.id, ing.id) in existing:
                    continue
                db.add(models.MenuIngredient(
                    menu_item_id=item.id, inventory_item_id=ing.id,
                    quantity_per_serving=qty, is_critical=critical,
                ))
                existing.add((item.id, ing.id))
                added += 1
    db.commit()
    return added


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import DATABASE_URL
    import os

    targets = [("local", DATABASE_URL)]
    if "--remote" in sys.argv:
        remote = os.getenv("REMOTE_DATABASE_URL")
        if remote:
            targets.append(("remote (Neon)", remote))

    for label, url in targets:
        engine = create_engine(url)
        Session = sessionmaker(bind=engine)
        db = Session()
        n = seed(db)
        total = db.execute(__import__("sqlalchemy").text("SELECT count(*) FROM menu_ingredients")).scalar()
        print(f"[{label}] added {n} recipe links; menu_ingredients now has {total} rows")
        db.close()


if __name__ == "__main__":
    main()
