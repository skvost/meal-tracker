"""Fake Supabase client and fixture data shared by the server tests and the dev server."""
from urllib.parse import parse_qs

from supabase_client import SupabaseError

TABLES = {
    "weekly_meals": [
        {"week_start": "2026-11-02", "meal_key": "s1", "category": "snidane", "meal_name": "Snídaně 1", "cover_name": "Jogurt", "total": 7},
        {"week_start": "2026-11-09", "meal_key": "s1", "category": "snidane", "meal_name": "Snídaně 1", "cover_name": "Jogurt", "total": 3},
        {"week_start": "2026-11-09", "meal_key": "s2", "category": "snidane", "meal_name": "Snídaně 2", "cover_name": "Vejce", "total": 4},
        {"week_start": "2026-11-09", "meal_key": "o", "category": "auto", "meal_name": "Oběd", "cover_name": "Hovězí + nudle", "total": 7},
        {"week_start": "2026-11-09", "meal_key": "v1", "category": "vecere", "meal_name": "Večeře 1", "cover_name": "Šunka + chléb", "total": 7},
    ],
    "meal_ingredients": [
        {"meal_key": "s1", "ingredient_key": "jogurt", "naty": 200, "filip": 400},
        {"meal_key": "s2", "ingredient_key": "vejce", "naty": 2, "filip": 3},
        {"meal_key": "o", "ingredient_key": "jogurt", "naty": 100, "filip": 100},
        {"meal_key": "v1", "ingredient_key": "sunka", "naty": 60, "filip": 100},
        {"meal_key": "v1", "ingredient_key": "chleba", "naty": 60, "filip": 100},
    ],
    "ingredients": [
        {"key": "jogurt", "name": "bílý jogurt", "unit": "g"},
        {"key": "vejce", "name": "vejce celé", "unit": "ks"},
        {"key": "sunka", "name": "šunka", "unit": "g"},
        {"key": "chleba", "name": "pečivo", "unit": "g"},
    ],
    "ingredient_nutrition": [
        {"ingredient_key": "jogurt", "kcal": 67, "protein": 3.9, "carbs": 4.4, "fat": 3.7, "grams_per_piece": None,
         "source": "rohlik", "product_id": 1, "note": None, "updated_at": "2026-11-10T21:00:00+00:00"},
        {"ingredient_key": "vejce", "kcal": 149, "protein": 13, "carbs": 0.9, "fat": 11, "grams_per_piece": 50,
         "source": "rohlik", "product_id": 2, "note": "1 ks M ≈ 50 g", "updated_at": "2026-11-10T21:00:00+00:00"},
        {"ingredient_key": "sunka", "kcal": 91, "protein": 19.3, "carbs": 0.5, "fat": 1.3, "grams_per_piece": None,
         "source": "estimate", "product_id": None, "note": "odhad", "updated_at": "2026-11-10T21:00:00+00:00"},
    ],
    "products": [
        {"product_id": 1, "name": "Miil jogurt 400 g", "ingredient_key": "jogurt"},
        {"product_id": 2, "name": "Vejce M 10 ks", "ingredient_key": "vejce"},
    ],
    "kcal_targets": [{"person": "naty", "kcal": 1500}, {"person": "filip", "kcal": 2400}],
}


class FakeClient:
    def __init__(self, tables=None):
        self.tables = tables if tables is not None else TABLES
        self.fail = False
        self.targets_set = []

    def select(self, table, query):
        if self.fail:
            raise SupabaseError("connect timeout")
        rows = list(self.tables.get(table, []))
        params = parse_qs(query)
        for key, values in params.items():
            if key in ("select", "order"):
                continue
            op, _, val = values[0].partition(".")
            if op == "eq":
                rows = [r for r in rows if str(r.get(key)) == val]
            elif op == "is" and val == "true":
                rows = [r for r in rows if r.get(key, True) is True]
        return rows

    def set_target(self, person, kcal):
        if self.fail:
            raise SupabaseError("connect timeout")
        self.targets_set.append((person, kcal))

    def clear_cache(self):
        pass
