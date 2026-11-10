"""Run the app against fixture data (no Supabase) on 127.0.0.1:8766 for UI checks."""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import App, serve  # noqa: E402
from tests.fixtures import FakeClient  # noqa: E402

if __name__ == "__main__":
    serve(App(FakeClient()), ["127.0.0.1"], int(sys.argv[1]) if len(sys.argv) > 1 else 8766)
    threading.Event().wait()
