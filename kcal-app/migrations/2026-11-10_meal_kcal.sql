-- Meal kcal: nutrition per ingredient and daily kcal targets. Additive only.
create table if not exists public.ingredient_nutrition (
  ingredient_key  text primary key references ingredients(key),
  kcal            numeric not null,          -- per 100 g
  protein         numeric not null,          -- g per 100 g
  carbs           numeric not null,
  fat             numeric not null,
  grams_per_piece numeric,                   -- required when ingredients.unit = 'ks'; edible weight
  source          text not null check (source in ('rohlik', 'estimate')),
  product_id      bigint,                    -- Rohlik product the values came from (source = 'rohlik')
  note            text,
  updated_at      timestamptz not null default now()
);

create table if not exists public.kcal_targets (
  person     text primary key check (person in ('naty', 'filip')),
  kcal       integer not null check (kcal > 0),
  updated_at timestamptz not null default now()
);
insert into public.kcal_targets (person, kcal) values ('naty', 1500), ('filip', 2400)
on conflict (person) do nothing;

alter table public.ingredient_nutrition enable row level security;
alter table public.kcal_targets         enable row level security;
-- No policies: only the service role can access these tables; anon is blocked.
