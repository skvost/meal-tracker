# Refreshing nutrition values

Nutrition lives in Supabase `ingredient_nutrition`, with one row per ingredient. The server never calls Rohlik itself.
To refresh, run these steps from a Claude session that has the **Rohlik** and **Supabase** MCP connectors (project `wooencmwsjoaguyhmsan`).

Run a refresh after `/meal-prep` switches an ingredient to a different preferred product, or after adding a new ingredient to `meal_ingredients`.

## Rules

- Rows with `source = 'rohlik'` are overwritten on each refresh.
- Rows with `source = 'estimate'` are only inserted when they are missing. They are **never overwritten**, because the user may have corrected them.
  To replace an estimate with Rohlik data, delete that row first.
- Amounts in `meal_ingredients` are raw or dry weights, so use values for the raw or dry product (dry pasta, dry rice, raw meat).
- `grams_per_piece` is required for every ingredient whose `ingredients.unit = 'ks'`. It is the edible weight of one piece.

## 1. Ingredients and their preferred products

```sql
select i.key, i.name, i.unit, i.on_rohlik, p.product_id, p.name as product
from ingredients i
left join products p on p.ingredient_key = i.key and p.preferred
where i.key in (select distinct ingredient_key from meal_ingredients)
order by i.key;
```

## 2. Rohlik nutrition

Call `get_products_composition_batch` with every non-null `product_id` from step 1.
For each product, take `nutritionalValues[0].values` where `portion = "100 g"`:
`energyKCal` → `kcal`, `protein` → `protein`, `carbohydrates` → `carbs`, and `fats` → `fat`.
Loose produce and fresh meat usually come back with an empty `nutritionalValues`. Those ingredients go to step 4.

## 3. Upsert the Rohlik rows

```sql
insert into ingredient_nutrition (ingredient_key, kcal, protein, carbs, fat, grams_per_piece, source, product_id, note) values
  ('<key>', <kcal>, <protein>, <carbs>, <fat>, <grams_per_piece or null>, 'rohlik', <product_id>, <note or null>)
  -- , ...
on conflict (ingredient_key) do update set
  kcal = excluded.kcal, protein = excluded.protein, carbs = excluded.carbs, fat = excluded.fat,
  grams_per_piece = coalesce(excluded.grams_per_piece, ingredient_nutrition.grams_per_piece),
  source = excluded.source, product_id = excluded.product_id,
  note = coalesce(excluded.note, ingredient_nutrition.note), updated_at = now()
where ingredient_nutrition.source = 'rohlik';
```

## 4. Estimates for items without Rohlik values

Use standard table values for the raw item, write the reason in `note` (in Czech), and set `source = 'estimate'`:

```sql
insert into ingredient_nutrition (ingredient_key, kcal, protein, carbs, fat, grams_per_piece, source, product_id, note) values
  ('<key>', <kcal>, <protein>, <carbs>, <fat>, <grams_per_piece or null>, 'estimate', null, '<why / source>')
on conflict (ingredient_key) do nothing;
```

These are the estimates currently in use (from the first fill on 2026-11-10):

| ingredient | per 100 g | g per piece | basis |
|---|---|---|---|
| banan | 89 kcal | 120 | table value; Rohlik banana weighs ~180 g with peel |
| jablko | 52 kcal | 150 | table value; Gala weighs ~170 g |
| brambory | 77 kcal | | raw potato |
| kureci_prsa | 110 kcal | | raw chicken breast |
| hovezi_steak | 155 kcal | | raw beef flank |
| zelenina | 20 kcal | | average of cucumber, cherry tomato, carrot, Chinese cabbage |
| protein | 360 kcal | | GymBeam Just Whey label (chocolate milkshake). It is not bought on Rohlik |

## 5. Check coverage

This query must return 0 rows:

```sql
select distinct mi.ingredient_key
from meal_ingredients mi
left join ingredient_nutrition n using (ingredient_key)
join ingredients i on i.key = mi.ingredient_key
where n.ingredient_key is null or (i.unit = 'ks' and n.grams_per_piece is null);
```

Then sanity-check the order with `select ingredient_key, kcal, source from ingredient_nutrition order by kcal desc;`.
Nuts and peanut butter should be ~600, dry pasta, rice and whey ~350, and vegetables 20–30 near the bottom. A value that is off by 10× is a units mistake.

The app caches Supabase reads for 60 s, so new values appear within a minute. No restart is needed.
