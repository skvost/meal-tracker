"""Calorie and macro calculation for one planned week. Pure functions, no I/O."""

PERSONS = ("naty", "filip")
MACROS = ("kcal", "protein", "carbs", "fat")
DAILY_TOTAL = 7
UNKNOWN_RECIPE = "recept neznámý"


def _grams(amount, unit, nutr):
    """Edible grams for one person's amount, or None when it cannot be known."""
    if not amount:
        return 0
    if nutr is None:
        return None
    if unit == "ks":
        per_piece = nutr.get("grams_per_piece")
        return None if per_piece is None else amount * per_piece
    return amount


def _round_macros(values):
    return {k: (round(v) if k == "kcal" else round(v, 1)) for k, v in values.items()}


def _meal(row, items, ingredients, nutrition):
    """Raw (unrounded) per-person totals plus the display structure for one weekly row."""
    if not row.get("meal_key") or not items:
        per_person = {p: {**{k: None for k in MACROS}, "incomplete": True} for p in PERSONS}
        return None, {"missing": [UNKNOWN_RECIPE], "per_person": per_person, "ingredients": []}

    raw = {p: {k: 0.0 for k in MACROS} for p in PERSONS}
    incomplete = {p: False for p in PERSONS}
    missing, lines = [], []
    for item in items:
        ing = ingredients.get(item["ingredient_key"], {"name": item["ingredient_key"], "unit": "g"})
        nutr = nutrition.get(item["ingredient_key"])
        line = {"name": ing["name"], "unit": ing["unit"], "amount": {}, "grams": {}, "kcal": {}, "missing": False}
        for p in PERSONS:
            amount = float(item.get(p) or 0)
            grams = _grams(amount, ing["unit"], nutr)
            line["amount"][p] = amount
            line["grams"][p] = grams
            if grams is None:
                line["kcal"][p] = None
                line["missing"] = True
                incomplete[p] = True
                continue
            for k in MACROS:
                raw[p][k] += grams * float(nutr[k]) / 100 if grams else 0.0
            line["kcal"][p] = round(grams * float(nutr["kcal"]) / 100) if grams else 0
        if line["missing"]:
            missing.append(ing["name"])
        lines.append(line)

    per_person = {p: {**_round_macros(raw[p]), "incomplete": incomplete[p]} for p in PERSONS}
    return (raw, incomplete), {"missing": missing, "per_person": per_person, "ingredients": lines}


def compute_week(rows, meal_ingredients, ingredients, nutrition, targets):
    by_meal = {}
    for item in meal_ingredients:
        by_meal.setdefault(item["meal_key"], []).append(item)

    meals = []
    computed = []  # (row, daily, raw-or-None, incomplete-or-None)
    for row in rows:
        daily = (row.get("total") or 0) >= DAILY_TOTAL
        result, display = _meal(row, by_meal.get(row.get("meal_key"), []), ingredients, nutrition)
        meals.append({
            "meal_key": row.get("meal_key"),
            "category": row["category"],
            "meal_name": row["meal_name"],
            "cover_name": row["cover_name"],
            "total": row.get("total") or 0,
            "daily": daily,
            **display,
        })
        computed.append((row, daily, result))

    people = {}
    for p in PERSONS:
        week = {k: 0.0 for k in MACROS}
        incomplete = False
        unknown_recipes = False
        known_meals = 0
        daily_kcal = 0.0
        options = {}  # category -> list of meal kcal for non-daily meals this person eats
        for row, daily, result in computed:
            if result is None:
                incomplete = unknown_recipes = True
                continue
            known_meals += 1
            raw, inc = result
            incomplete = incomplete or inc[p]
            total = row.get("total") or 0
            for k in MACROS:
                week[k] += raw[p][k] * total
            if daily:
                daily_kcal += raw[p]["kcal"]
            elif raw[p]["kcal"] > 0:
                options.setdefault(row["category"], []).append(raw[p]["kcal"])

        target = targets.get(p)
        if not known_meals:
            # No recipe known for this week (e.g. weeks before meal_key existed): nothing to show, not "0 kcal".
            people[p] = {"target": target, "avg": {k: None for k in MACROS}, "min_day": None, "max_day": None,
                         "diff": None, "diff_pct": None, "incomplete": True, "known": False,
                         "unknown_recipes": unknown_recipes}
            continue
        avg = {k: v / DAILY_TOTAL for k, v in week.items()}
        diff = avg["kcal"] - target if target else None
        people[p] = {
            "target": target,
            "avg": _round_macros(avg),
            "min_day": round(daily_kcal + sum(min(v) for v in options.values())),
            "max_day": round(daily_kcal + sum(max(v) for v in options.values())),
            "diff": round(diff) if diff is not None else None,
            "diff_pct": round(100 * diff / target) if target else None,
            "incomplete": incomplete,
            "known": True,
            "unknown_recipes": unknown_recipes,
        }

    return {"people": people, "meals": meals}
