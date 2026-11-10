"""Minimal Supabase REST (PostgREST) client using only the standard library."""
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class SupabaseError(Exception):
    """Any failure talking to Supabase. The message never contains the API key."""


class SupabaseClient:
    def __init__(self, url, key, ttl=60, timeout=10):
        self._base = url.rstrip("/") + "/rest/v1/"
        self._key = key
        self._ttl = ttl
        self._timeout = timeout
        self._cache = {}
        self._lock = threading.Lock()

    def _request(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self._base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("apikey", self._key)
        req.add_header("Authorization", "Bearer " + self._key)
        req.add_header("Accept", "application/json")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                payload = json.loads(e.read() or b"{}")
                detail = payload.get("message") or payload.get("error") or ""
            except (ValueError, AttributeError):
                pass
            raise SupabaseError("Supabase HTTP %d: %s" % (e.code, detail or e.reason)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise SupabaseError("Supabase nedostupný: %s" % reason) from None

    def select(self, table, query):
        cache_key = (table, query)
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(cache_key)
            if hit and now - hit[0] < self._ttl:
                return hit[1]
        _, _, raw = self._request("GET", "%s?%s" % (table, query))
        try:
            rows = json.loads(raw)
        except ValueError:
            raise SupabaseError("Supabase vrátil neplatnou odpověď") from None
        with self._lock:
            self._cache[cache_key] = (now, rows)
        return rows

    def set_target(self, person, kcal):
        body = {"kcal": kcal, "updated_at": datetime.now(timezone.utc).isoformat()}
        _, headers, _ = self._request("PATCH", "kcal_targets?person=eq.%s" % person, body,
                                      {"Prefer": "return=minimal,count=exact"})
        if (headers.get("Content-Range") or "").endswith("/0"):
            raise SupabaseError("Cíl pro '%s' v databázi neexistuje" % person)
        self.clear_cache()

    def clear_cache(self):
        with self._lock:
            self._cache.clear()
