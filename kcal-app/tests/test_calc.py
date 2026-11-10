import copy
import unittest

from calc import compute_week

INGREDIENTS = {
    "jogurt": {"name": "jogurt", "unit": "g"},
    "vejce": {"name": "vejce", "unit": "ks"},
    "x": {"name": "x name", "unit": "g"},
}
NUTRITION = {
    "jogurt": {"kcal": 67, "protein": 3.9, "carbs": 4.4, "fat": 3.7, "grams_per_piece": None},
    "vejce": {"kcal": 149, "protein": 13, "carbs": 0.9, "fat": 11, "grams_per_piece": 50},
}
ROWS = [
    {"meal_key": "s1", "category": "snidane", "meal_name": "Snídaně 1", "cover_name": "Jogurt", "total": 3},
    {"meal_key": "s2", "category": "snidane", "meal_name": "Snídaně 2", "cover_name": "Vejce", "total": 4},
    {"meal_key": "o", "category": "auto", "meal_name": "Oběd", "cover_name": "Jogurt", "total": 7},
]
MEAL_INGREDIENTS = [
    {"meal_key": "s1", "ingredient_key": "jogurt", "naty": 200, "filip": 400},
    {"meal_key": "s2", "ingredient_key": "vejce", "naty": 2, "filip": 3},
    {"meal_key": "o", "ingredient_key": "jogurt", "naty": 100, "filip": 100},
]
TARGETS = {"naty": 1500, "filip": 2400}


def run(rows=ROWS, mi=MEAL_INGREDIENTS, ingredients=INGREDIENTS, nutrition=NUTRITION):
    return compute_week(rows, mi, ingredients, nutrition, TARGETS)


def meal(result, key):
    return next(m for m in result["meals"] if m["meal_key"] == key)


class ComputeWeekTest(unittest.TestCase):
    def test_grams_meal(self):
        s1 = meal(run(), "s1")
        self.assertEqual(s1["per_person"]["naty"]["kcal"], 134)
        self.assertEqual(s1["per_person"]["filip"]["kcal"], 268)

    def test_piece_meal(self):
        s2 = meal(run(), "s2")
        self.assertEqual(s2["per_person"]["naty"]["kcal"], 149)
        self.assertEqual(s2["per_person"]["filip"]["kcal"], 224)
        self.assertEqual(s2["ingredients"][0]["grams"], {"naty": 100, "filip": 150})

    def test_daily_detection(self):
        r = run()
        self.assertTrue(meal(r, "o")["daily"])
        self.assertFalse(meal(r, "s1")["daily"])
        self.assertFalse(meal(r, "s2")["daily"])

    def test_average_day(self):
        self.assertEqual(run()["people"]["naty"]["avg"]["kcal"], 210)

    def test_min_max_day(self):
        naty = run()["people"]["naty"]
        self.assertEqual(naty["min_day"], 67 + 134)
        self.assertEqual(naty["max_day"], 67 + 149)

    def test_target_diff(self):
        naty = run()["people"]["naty"]
        self.assertEqual(naty["target"], 1500)
        self.assertEqual(naty["diff"], 210 - 1500)
        self.assertEqual(naty["diff_pct"], round(100 * (210 - 1500) / 1500))
        self.assertFalse(naty["incomplete"])

    def test_missing_nutrition(self):
        mi = MEAL_INGREDIENTS + [{"meal_key": "s1", "ingredient_key": "x", "naty": 50, "filip": 50}]
        r = run(mi=mi)
        s1 = meal(r, "s1")
        self.assertEqual(s1["missing"], ["x name"])
        self.assertEqual(s1["per_person"]["naty"]["kcal"], 134)
        self.assertTrue(s1["per_person"]["naty"]["incomplete"])
        self.assertTrue(r["people"]["naty"]["incomplete"])

    def test_piece_without_weight_is_missing(self):
        nutrition = copy.deepcopy(NUTRITION)
        nutrition["vejce"]["grams_per_piece"] = None
        s2 = meal(run(nutrition=nutrition), "s2")
        self.assertEqual(s2["missing"], ["vejce"])
        self.assertEqual(s2["ingredients"][0]["grams"], {"naty": None, "filip": None})
        self.assertTrue(s2["ingredients"][0]["missing"])

    def test_row_without_meal_key(self):
        rows = ROWS + [{"meal_key": None, "category": "vecere", "meal_name": "Večeře 9", "cover_name": "?", "total": 2}]
        r = run(rows=rows)
        old = next(m for m in r["meals"] if m["meal_name"] == "Večeře 9")
        self.assertEqual(old["missing"], ["recept neznámý"])
        self.assertIsNone(old["per_person"]["naty"]["kcal"])
        self.assertEqual(r["people"]["naty"]["avg"]["kcal"], 210)
        self.assertTrue(r["people"]["naty"]["incomplete"])

    def test_person_absent_from_category(self):
        rows = ROWS + [
            {"meal_key": "va", "category": "vecere", "meal_name": "Večeře A", "cover_name": "", "total": 3},
            {"meal_key": "vb", "category": "vecere", "meal_name": "Večeře B", "cover_name": "", "total": 4},
        ]
        mi = MEAL_INGREDIENTS + [
            {"meal_key": "va", "ingredient_key": "jogurt", "naty": 0, "filip": 100},
            {"meal_key": "vb", "ingredient_key": "jogurt", "naty": 0, "filip": 100},
        ]
        people = run(rows=rows, mi=mi)["people"]
        self.assertEqual(people["naty"]["min_day"], 201)
        self.assertEqual(people["naty"]["max_day"], 216)
        # filip: o 67 + snidane min(268, 224) / max + vecere 67
        self.assertEqual(people["filip"]["min_day"], 67 + 224 + 67)
        self.assertEqual(people["filip"]["max_day"], 67 + 268 + 67)

    def test_zero_amount_not_counted(self):
        mi = [dict(r) for r in MEAL_INGREDIENTS]
        mi[0]["filip"] = 0
        s1 = meal(run(mi=mi), "s1")
        self.assertEqual(s1["per_person"]["filip"]["kcal"], 0)
        self.assertEqual(s1["ingredients"][0]["grams"]["filip"], 0)
        self.assertFalse(s1["ingredients"][0]["missing"])
        self.assertEqual(s1["missing"], [])


if __name__ == "__main__":
    unittest.main()
