#!/usr/bin/env python3
"""
Copy the web app into the Android Chaquopy package.
============================================================

The Android build needs its own copy of app.py, templates/, static/ and
data/ inside `android/app/src/main/python/kotoba_app/`, because that
directory is what gets packaged into the APK.

Keeping two hand-maintained copies is how the two versions quietly drift
apart, so this script makes the top-level app the single source of truth
and regenerates the Android copy from it. CI runs it before every build;
run it yourself after editing anything under templates/ or static/:

    python sync_android.py

The only difference between the two copies of app.py is the `run_server`
entry point appended here, which MainActivity calls through Chaquopy.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
TARGET = ROOT / "android" / "app" / "src" / "main" / "python" / "kotoba_app"

# Directories copied wholesale.
TREES = ["templates", "static", "data"]

# Files the running app writes to itself - never ship a stale copy.
RUNTIME_FILES = {"streak.json", "feedback.json", "users.json", "user_streaks.json", "progress.json", "user_progress.json", "secret_key.txt"}

RUN_SERVER = '''

def run_server():
    """Entry point called from Android's MainActivity via Chaquopy.
    debug=False and use_reloader=False: Flask's reloader forks a second
    process to watch for file changes, which doesn't work inside
    Chaquopy's restricted process model and isn't needed in a packaged
    app anyway. threaded=True lets the WebView issue a few requests in
    parallel (e.g. a page load plus its own async fetch calls) without
    queuing behind a single-threaded dev server.
    """
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)
'''


def ignored(_dir, names):
    return [
        n for n in names
        if n in RUNTIME_FILES or n == "__pycache__" or n.endswith(".pyc")
    ]


def main():
    if not (ROOT / "app.py").exists():
        print("app.py not found - run this from the project root", file=sys.stderr)
        return 1

    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "__init__.py").touch()

    for tree in TREES:
        src = ROOT / tree
        if not src.is_dir():
            print(f"skipping {tree}/ (not present)")
            continue
        dst = TARGET / tree
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=ignored)
        print(f"synced {tree}/")

    source = (ROOT / "app.py").read_text(encoding="utf-8").rstrip("\n")
    (TARGET / "app.py").write_text(source + "\n" + RUN_SERVER, encoding="utf-8")
    print("synced app.py (+ run_server)")

    print(f"\nAndroid package is up to date: {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
