#!/usr/bin/env python3
"""Minimal test runner for environments without pytest installed (this build
sandbox is one; your Windows machine almost certainly has pytest available
via `pip install pytest` and should just use that instead — see README.md).

Discovers every tests/test_*.py module, runs every top-level test_* function,
prints PASS/FAIL per test, and exits non-zero on any failure.
"""
import importlib
import pkgutil
import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    import tests
    total = failed = 0
    for _, modname, _ in pkgutil.iter_modules(tests.__path__, prefix="tests."):
        if not modname.rsplit(".", 1)[-1].startswith("test_"):
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception as e:
            print(f"IMPORT ERROR {modname}: {e}")
            failed += 1
            continue
        for name in dir(mod):
            if name.startswith("test_"):
                total += 1
                fn = getattr(mod, name)
                try:
                    fn()
                    print(f"PASS  {modname}.{name}")
                except Exception:
                    failed += 1
                    print(f"FAIL  {modname}.{name}")
                    traceback.print_exc()
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
