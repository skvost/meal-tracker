# Meal kcal: design

Date: 2026-11-10
Status: approved in chat, awaiting spec review

## Goal

A locally hosted app that shows every meal in the current plan with its calories for each person, and each
person's daily calorie intake compared with a target. Calories must be based on the products actually bought
on Rohlik, not on generic tables, wherever Rohlik has the data.

Success means: Naty and Filip can open one page and see (1) kcal per meal per person, (2) an average day,
the lightest day and the heaviest day per person, and (3) how the average day compares with their target.

## Decisions

| Topic | Decision |
|---|---|
| Purpose | Compare kcal (and macros) with a daily target per person |
| Targets | Start at Naty 1500 kcal, Filip 2400 kcal. The user is unsure of these, so they are editable in the app |
| Where it runs | The Linux box. Reachable on localhost and the Tailscale address only, never on a public interface |
| Architecture | Small backend server. All data lives in the existing Supabase project; there is no local database |
| Stack | Python 3.12 standard library only (`http.server`, `urllib`, `json`). No packages, so very little memory is used |

## Architecture

```
browser ──HTTP──> kcal server (:8765, Python stdlib) ──HTTPS + service_role key──> Supabase REST
                                                                                     ├─ weekly_meals (existing)
                                                                                     ├─ meal_ingredients (existing)
                                                                                     ├─ ingredients (existing)
                                                                                     ├─ products (existing)
                                                                                     ├─ ingredient_nutrition (new)
                                                                                     └─ kcal_targets (new)
Claude session ──Rohlik MCP──> nutrition per product ──Supabase MCP──> ingredient_nutrition
```

- The server lives in `kcal-app/` in this repo. It serves one HTML page and a small JSON API, and does the calculation.
- The Supabase `service_role` key is kept only on this box, in `~/.config/meal-kcal/env` (mode 600). It is never
  committed, logged, or sent to the browser.
- The server caches Supabase reads for 60 s. Saving a target clears the cache.

## Data model (Supabase, additive only)

The migration only adds tables. Existing tables, functions, and policies are not changed. The SQL is saved in `kcal-app/migrations/`.

```sql
create table public.ingredient_nutrition (
  ingredient_key  text primary key references ingredients(key),
  kcal            numeric not null,          -- per 100 g
  protein         numeric not null,          -- g per 100 g
  carbs           numeric not null,
  fat             numeric not null,
  grams_per_piece numeric,                   -- required when ingredients.unit = 'ks'; edible weight
  source          text not null check (source in ('rohlik', 'estimate')),
  product_id      bigint,                    -- Rohlik product the values came from (when source = 'rohlik')
  note            text,                      -- e.g. "banana ~180 g with peel, ~120 g edible"
  updated_at      timestamptz not null default now()
);

create table public.kcal_targets (
  person     text primary key check (person in ('naty', 'filip')),
  kcal       integer not null check (kcal > 0),
  updated_at timestamptz not null default now()
);
insert into public.kcal_targets (person, kcal) values ('naty', 1500), ('filip', 2400);

alter table public.ingredient_nutrition enable row level security;
alter table public.kcal_targets         enable row level security;
-- No policies: like the other tables, only the service role can access them. anon is blocked.
```

## Calculation

The inputs are the selected week's `weekly_meals` rows (`meal_key`, `category`, `total`), the current `meal_ingredients` (grams per person as numbers),
`ingredients.unit`, `ingredient_nutrition`, and `kcal_targets`. The default week is the latest `week_start`.

- **Amount in grams:** if `unit = 'g'`, the amount is the grams. If `unit = 'ks'`, it is pieces × `grams_per_piece`.
- **Meal, per person:** Σ over ingredients of grams × value / 100, computed for kcal, protein, carbs, and fat. An amount of 0 means the person does not eat that ingredient.
- **Missing nutrition:** an ingredient without an `ingredient_nutrition` row, or a `ks` ingredient without `grams_per_piece`, is
  never counted as 0. The meal is shown as a lower bound ("≥ X kcal") with a warning that names the ingredient. Every total that includes it is marked the same way.
- **Average day, per person:** Σ(meal kcal × `total`) / 7.
- **Daily meals:** rows with `total >= 7` are eaten every day, for example the lunch and Filip's daily svačina. They count in every day.
- **Lightest and heaviest day, per person:** the daily meals, plus the lowest or highest meal from each of the remaining categories
  (snídaně, svačiny, večeře). Only meals in which that person has at least one ingredient are considered.
- **Target comparison:** the average day minus the target, in kcal and as a percentage.

The planned amounts for the current week are what is shown. Ticked `count` values (what was actually eaten) are out of scope.

## Screens

There is one page, in Czech, using the same colour tokens as `index.html`, with a week picker at the top.

1. **Person cards (Naty, Filip).** Each card shows the average day against the target as a bar with the difference, the lightest–heaviest range, and average protein, carbs, and fat in grams.
   The target is edited inline and saved to `kcal_targets`.
2. **Meals by category.** Each row shows the meal name, the cover name, ×total, Naty's kcal, and Filip's kcal. Expanding a row shows a per-ingredient table
   (grams and kcal per person) and the meal's macros. Meals with missing nutrition show a warning badge.
3. **Ingredients tab** (read-only). Each ingredient is listed with its Rohlik product, kcal per 100 g, grams per piece, and source (Rohlik and date, or estimate).
   Missing ingredients are listed first and highlighted.

## API

- `GET /` returns the page.
- `GET /api/week?start=YYYY-MM-DD` returns the computed JSON for the page. Without `start`, it uses the latest week. The response also lists the available weeks.
- `GET /api/ingredients` returns the ingredient, nutrition, and source table.
- `PUT /api/targets/{naty|filip}` with body `{"kcal": 1500}` validates that the value is a positive integer below 10000, then saves it.

## Nutrition refresh (Claude-run procedure)

The Rohlik and Supabase connectors are reachable only from a Claude session, so the refresh is a written procedure
(`kcal-app/REFRESH.md`), not something the server does:

1. Read `ingredients` (where `on_rohlik`) and `products` (where `preferred`) from Supabase.
2. Call `get_products_composition_batch` for the preferred product IDs.
3. Upsert `ingredient_nutrition` with `source='rohlik'`, `product_id`, and `updated_at`.
4. For ingredients without Rohlik nutrition (loose produce, mixes), keep or insert values marked `source='estimate'` with a note.
   The starting estimates are:
   - egg M: ~50 g edible per piece
   - egg white: ~33 g per piece
   - banana: ~120 g edible per piece
   - apple: ~150 g per piece
   - zelenina mix (cucumber, cherry tomato, carrot, Chinese cabbage): ~20 kcal per 100 g
   - potatoes: ~77 kcal per 100 g
   - frozen wok vegetables: taken from the product if it can be found, otherwise an estimate
5. "protein" (powder) and "ořechové máslo" are not in recent orders. Ask the user which products they are. Until then they stay
   missing and are shown as warnings.

## Running

- `kcal-app/server.py` binds to `127.0.0.1` and the Tailscale address on port 8765.
- A systemd user service, `meal-kcal.service`, has `Restart=on-failure` and starts at boot (linger enabled).
- The server reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from `~/.config/meal-kcal/env`. If either is missing, it exits with a clear message.

## Errors

- **Supabase paused or unreachable:** the page shows "Supabase je uspaný nebo nedostupný" with the error detail. Restoring it is a manual step
  through the Supabase connector.
- **Supabase returns an error on read:** the API returns 502 with the message, and the page shows it. Old numbers are never shown as if they were current.
- **Invalid target value:** the API returns 400, and the page keeps the previous value.

## Testing

- Unit tests (`python3 -m unittest`, stdlib only) for the calculation module using fixture data: g and ks conversion, a missing
  nutrition lower bound, a missing `grams_per_piece`, daily-meal detection, the average day, the lightest and heaviest day, and a person with zero amounts in a meal.
- A manual check against live data: one meal per person calculated by hand from Supabase and Rohlik values, and compared with the app.
- A smoke check of the running service: `curl` each endpoint, and take a screenshot of the page.

## Out of scope

Tracking actual intake from `count`, history across weeks, editing recipes or nutrition in the UI, showing kcal on the public
GitHub Pages site, and changes to `/meal-prep`.

## Prerequisites from the user

1. Connect the Supabase connector in this Claude session (`/mcp`). It is used for the migration and the refresh.
2. Put the `service_role` key in `~/.config/meal-kcal/env` on this box (exact command given at build time).
