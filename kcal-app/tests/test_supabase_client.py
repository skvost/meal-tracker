import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from supabase_client import SupabaseClient, SupabaseError

KEY = "secret-service-key"


class Stub(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _reply(self, status, body, headers=()):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Stub.calls.append(("GET", self.path, self.headers.get("apikey"), self.headers.get("Authorization")))
        if self.path.startswith("/rest/v1/broken"):
            self._reply(400, {"message": "column x does not exist"})
        else:
            self._reply(200, [{"ok": 1}])

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length))
        Stub.calls.append(("PATCH", self.path, body))
        rng = "*/0" if "person=eq.nobody" in self.path else "0-0/1"
        self._patch_reply(rng)

    def _patch_reply(self, rng):
        self.send_response(204)
        self.send_header("Content-Range", rng)
        self.end_headers()


class SupabaseClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        Stub.calls.clear()

    def test_select_sends_key_and_caches(self):
        c = SupabaseClient(self.url, KEY)
        self.assertEqual(c.select("meals", "select=*"), [{"ok": 1}])
        self.assertEqual(c.select("meals", "select=*"), [{"ok": 1}])
        self.assertEqual(len(Stub.calls), 1)
        _, path, apikey, auth = Stub.calls[0]
        self.assertEqual(path, "/rest/v1/meals?select=*")
        self.assertEqual(apikey, KEY)
        self.assertEqual(auth, "Bearer " + KEY)
        c.clear_cache()
        c.select("meals", "select=*")
        self.assertEqual(len(Stub.calls), 2)

    def test_http_error_carries_postgrest_message(self):
        with self.assertRaises(SupabaseError) as ctx:
            SupabaseClient(self.url, KEY).select("broken", "select=*")
        self.assertIn("column x does not exist", str(ctx.exception))
        self.assertNotIn(KEY, str(ctx.exception))

    def test_unreachable_raises_supabase_error(self):
        with self.assertRaises(SupabaseError) as ctx:
            SupabaseClient("http://127.0.0.1:9", KEY, timeout=2).select("meals", "select=*")
        self.assertNotIn(KEY, str(ctx.exception))

    def test_set_target_patches_and_clears_cache(self):
        c = SupabaseClient(self.url, KEY)
        c.select("kcal_targets", "select=person,kcal")
        c.set_target("naty", 1600)
        method, path, body = Stub.calls[1]
        self.assertEqual((method, path), ("PATCH", "/rest/v1/kcal_targets?person=eq.naty"))
        self.assertEqual(body["kcal"], 1600)
        self.assertIn("T", body["updated_at"])
        c.select("kcal_targets", "select=person,kcal")
        self.assertEqual(len(Stub.calls), 3)

    def test_set_target_zero_rows_raises(self):
        with self.assertRaises(SupabaseError):
            SupabaseClient(self.url, KEY).set_target("nobody", 1600)


if __name__ == "__main__":
    unittest.main()
