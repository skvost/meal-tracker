# Meal kcal

A local web app that shows kcal and macros for every meal in the current week's plan, for Naty and Filip,
plus each person's average, lightest and heaviest day against a daily target.

- Meals and per-person grams come live from Supabase (`weekly_meals`, `meal_ingredients`).
- Nutrition comes from `ingredient_nutrition`, filled from Rohlik product data. See [REFRESH.md](REFRESH.md).
- Targets are stored in `kcal_targets` and can be edited on the page.

Design: `docs/superpowers/specs/2026-11-10-meal-kcal-design.md`.

## Open it

- On the box: http://localhost:8765/
- From the Mac or phone (Tailscale): `http://<tailscale ip>:8765/`
- Ingredients tab directly: append `#suroviny`

## Run

The server uses only the Python 3 standard library and needs `~/.config/meal-kcal/env` (mode 600):

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key>
BIND_ADDRS=127.0.0.1,<tailscale ip>
```

It runs as a systemd user service:

```sh
ln -sf ~/code/meal-tracker/kcal-app/meal-kcal.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now meal-kcal
systemctl --user status meal-kcal        # logs: journalctl --user -u meal-kcal
```

After changing code, run `systemctl --user restart meal-kcal`. Data changes in Supabase appear within 60 s without a restart.

If the page says **"Supabase je uspaný nebo nedostupný"**, the project has probably auto-paused.
Restore it from a Claude session with the Supabase connector (`get_project`, then `restore_project`).

## Tests

```sh
cd kcal-app && python3 -m unittest -v
python3 tests/devserver.py 8766   # UI against fixture data, no Supabase needed
```
