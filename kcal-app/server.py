"""Meal kcal: local web server. Python stdlib only.

Reads Supabase with the service_role key from ~/.config/meal-kcal/env and serves static/index.html plus a JSON API.
"""
import json
import logging
import os
import re
import socket
import sys
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from calc import PERSONS, compute_week
from supabase_client import SupabaseClient, SupabaseError

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "static", "index.html")
CONFIG_PATH = os.path.expanduser("~/.config/meal-kcal/env")
PORT = 8765
MAX_TARGET = 10000
IP_FREEBIND = getattr(socket, "IP_FREEBIND", 15)  # Linux

log = logging.getLogger("meal-kcal")


class App:
    def __init__(self, client):
        self.client = client

    def _targets(self):
        return {r["person"]: r["kcal"] for r in self.client.select("kcal_targets", "select=person,kcal")}

    def week(self, start):
        if start is not None:
            try:
                start = date.fromisoformat(start).isoformat()
            except ValueError:
                return 400, {"error": "Neplatné datum týdne: %s" % start}
        try:
            # Ordered newest first so PostgREST's row cap (max_rows) can only ever drop the oldest weeks.
            weeks = sorted({r["week_start"] for r in self.client.select(
                "weekly_meals", "select=week_start&order=week_start.desc")}, reverse=True)
            week = start or (weeks[0] if weeks else None)
            rows = []
            if week:
                rows = self.client.select(
                    "weekly_meals",
                    "select=meal_key,category,meal_name,cover_name,total&week_start=eq.%s&order=id" % week)
            ingredients = {r["key"]: r for r in self.client.select("ingredients", "select=key,name,unit")}
            nutrition = {r["ingredient_key"]: r for r in self.client.select("ingredient_nutrition", "select=*")}
            meal_ingredients = self.client.select("meal_ingredients", "select=*")
            targets = self._targets()
        except SupabaseError as e:
            return 502, {"error": str(e)}
        result = compute_week(rows, meal_ingredients, ingredients, nutrition, targets)
        return 200, {"week": week, "weeks": weeks, **result}

    def ingredients(self):
        try:
            ingredients = self.client.select("ingredients", "select=key,name,unit")
            nutrition = {r["ingredient_key"]: r for r in self.client.select("ingredient_nutrition", "select=*")}
            products = {r["ingredient_key"]: r["name"]
                        for r in self.client.select("products", "select=ingredient_key,name&preferred=is.true")}
            used = {r["ingredient_key"] for r in self.client.select("meal_ingredients", "select=*")}
        except SupabaseError as e:
            return 502, {"error": str(e)}
        out = []
        for ing in ingredients:
            if ing["key"] not in used:
                continue
            n = nutrition.get(ing["key"]) or {}
            missing = not n or (ing["unit"] == "ks" and n.get("grams_per_piece") is None)
            out.append({
                "key": ing["key"], "name": ing["name"], "unit": ing["unit"],
                **{k: n.get(k) for k in ("kcal", "protein", "carbs", "fat", "grams_per_piece",
                                         "source", "product_id", "note", "updated_at")},
                "product_name": products.get(ing["key"]),
                "missing": missing,
            })
        out.sort(key=lambda r: (not r["missing"], r["name"]))
        return 200, {"ingredients": out}

    def put_target(self, person, raw_body):
        if person not in PERSONS:
            return 404, {"error": "Neznámá osoba: %s" % person}
        try:
            kcal = json.loads(raw_body or b"").get("kcal")
        except (ValueError, AttributeError):
            return 400, {"error": "Neplatný požadavek"}
        if not isinstance(kcal, int) or isinstance(kcal, bool) or not 0 < kcal < MAX_TARGET:
            return 400, {"error": "Cíl musí být celé číslo mezi 1 a %d kcal" % (MAX_TARGET - 1)}
        try:
            self.client.set_target(person, kcal)
        except SupabaseError as e:
            return 502, {"error": str(e)}
        return 200, {"person": person, "kcal": kcal}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "meal-kcal"

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _json(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                with open(INDEX, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            elif url.path == "/api/week":
                start = parse_qs(url.query).get("start", [None])[0]
                self._json(*app.week(start))
            elif url.path == "/api/ingredients":
                self._json(*app.ingredients())
            else:
                self._json(404, {"error": "Nenalezeno"})

        def do_PUT(self):
            m = re.fullmatch(r"/api/targets/([a-z]+)", urlparse(self.path).path)
            if not m:
                return self._json(404, {"error": "Nenalezeno"})
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            self._json(*app.put_target(m.group(1), self.rfile.read(length)))

    return Handler


class FreebindHTTPServer(ThreadingHTTPServer):
    """Binds even when the address is not configured yet (e.g. Tailscale still starting at boot)."""

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IP, IP_FREEBIND, 1)
        super().server_bind()


def serve(app, addrs, port):
    """Start one server thread per address; skip addresses that cannot be bound."""
    handler = make_handler(app)
    servers = []
    for addr in addrs:
        try:
            httpd = FreebindHTTPServer((addr, port), handler)
        except OSError as e:
            log.warning("cannot bind %s:%s (%s), skipping", addr, port, e)
            continue
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        log.info("serving on http://%s:%d/", addr, httpd.server_address[1])
        servers.append(httpd)
    if not servers:
        raise SystemExit("meal-kcal: could not bind any of %s on port %s" % (addrs, port))
    return servers


def load_config(path):
    cfg = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        raise SystemExit("meal-kcal: config file %s not found" % path) from None
    for required in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        if not cfg.get(required):
            raise SystemExit("meal-kcal: missing %s in %s" % (required, path))
    return cfg


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    cfg = load_config(CONFIG_PATH)
    client = SupabaseClient(cfg["SUPABASE_URL"], cfg["SUPABASE_SERVICE_KEY"])
    addrs = [a.strip() for a in cfg.get("BIND_ADDRS", "127.0.0.1").split(",") if a.strip()]
    serve(App(client), addrs, int(cfg.get("PORT", PORT)))
    threading.Event().wait()


if __name__ == "__main__":
    main()
