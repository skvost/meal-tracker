import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request

from server import App, load_config, serve
from tests.fixtures import FakeClient


class AppWeekTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.app = App(self.client)

    def test_week_latest_by_default(self):
        status, body = self.app.week(None)
        self.assertEqual(status, 200)
        self.assertEqual(body["week"], "2026-11-09")
        self.assertEqual(body["weeks"], ["2026-11-09", "2026-11-02"])
        self.assertEqual(len(body["meals"]), 4)
        self.assertIn("naty", body["people"])

    def test_week_explicit_start(self):
        status, body = self.app.week("2026-11-02")
        self.assertEqual(status, 200)
        self.assertEqual(body["week"], "2026-11-02")
        self.assertEqual([m["meal_key"] for m in body["meals"]], ["s1"])

    def test_week_bad_start_returns_400(self):
        status, body = self.app.week("2026-13-99")
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_week_supabase_down_returns_502(self):
        self.client.fail = True
        status, body = self.app.week(None)
        self.assertEqual(status, 502)
        self.assertIn("connect timeout", body["error"])

    def test_week_no_data(self):
        app = App(FakeClient({"kcal_targets": [{"person": "naty", "kcal": 1500}, {"person": "filip", "kcal": 2400}]}))
        status, body = app.week(None)
        self.assertEqual(status, 200)
        self.assertEqual(body["weeks"], [])
        self.assertEqual(body["meals"], [])


class AppTargetsTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.app = App(self.client)

    def test_put_target_ok(self):
        status, body = self.app.put_target("naty", b'{"kcal": 1600}')
        self.assertEqual(status, 200)
        self.assertEqual(self.client.targets_set, [("naty", 1600)])

    def test_put_target_invalid(self):
        for person, raw in [("naty", b'{"kcal": 0}'), ("naty", b'{"kcal": 10000}'), ("naty", b'{"kcal": "x"}'),
                            ("naty", b'nope'), ("naty", b'{"kcal": 1500.5}'), ("naty", b'{"kcal": true}'),
                            ("pepa", b'{"kcal": 1600}')]:
            status, body = self.app.put_target(person, raw)
            self.assertIn(status, (400, 404), (person, raw))
            self.assertIn("error", body)
        self.assertEqual(self.client.targets_set, [])


class AppIngredientsTest(unittest.TestCase):
    def test_ingredients_missing_first(self):
        status, body = App(FakeClient()).ingredients()
        self.assertEqual(status, 200)
        rows = body["ingredients"]
        self.assertEqual(rows[0]["key"], "chleba")
        self.assertTrue(rows[0]["missing"])
        self.assertFalse(any(r["missing"] for r in rows[1:]))
        jogurt = next(r for r in rows if r["key"] == "jogurt")
        self.assertEqual(jogurt["product_name"], "Miil jogurt 400 g")
        self.assertEqual(jogurt["kcal"], 67)


class ConfigTest(unittest.TestCase):
    def test_load_config_missing_key(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("SUPABASE_URL=https://example.supabase.co\n")
        try:
            with self.assertRaises(SystemExit) as ctx:
                load_config(f.name)
            self.assertIn("SUPABASE_SERVICE_KEY", str(ctx.exception.code))
        finally:
            os.unlink(f.name)

    def test_load_config_ok(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("# comment\nSUPABASE_URL=https://example.supabase.co\nSUPABASE_SERVICE_KEY=abc=def\nBIND_ADDRS=127.0.0.1\n")
        try:
            cfg = load_config(f.name)
            self.assertEqual(cfg["SUPABASE_SERVICE_KEY"], "abc=def")
            self.assertEqual(cfg["BIND_ADDRS"], "127.0.0.1")
        finally:
            os.unlink(f.name)


class HttpTest(unittest.TestCase):
    def test_bind_skips_unavailable_address(self):
        servers = serve(App(FakeClient()), ["127.0.0.1", "203.0.113.1"], 0)
        try:
            self.assertEqual(len(servers), 1)
        finally:
            for s in servers:
                s.shutdown()
                s.server_close()

    def test_http_routes(self):
        client = FakeClient()
        servers = serve(App(client), ["127.0.0.1"], 0)
        base = "http://127.0.0.1:%d" % servers[0].server_address[1]
        try:
            with urllib.request.urlopen(base + "/api/week") as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(json.load(r)["week"], "2026-11-09")
            with urllib.request.urlopen(base + "/") as r:
                self.assertEqual(r.status, 200)
                self.assertIn("text/html", r.headers["Content-Type"])
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/nope")
            self.assertEqual(ctx.exception.code, 404)
            req = urllib.request.Request(base + "/api/targets/filip", data=b'{"kcal": 2500}', method="PUT")
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
            self.assertEqual(client.targets_set, [("filip", 2500)])
        finally:
            for s in servers:
                s.shutdown()
                s.server_close()


if __name__ == "__main__":
    unittest.main()
