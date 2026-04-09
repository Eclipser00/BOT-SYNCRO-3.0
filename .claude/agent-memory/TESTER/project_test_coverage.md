---
name: Test coverage map
description: Which source files have test coverage and where the test files live
type: project
---

`backtest bot v7.0 syncro/download_mt5_data.py` is covered by `backtest bot v7.0 syncro/test_download_mt5_data.py` (created 2026-04-09).

**Why:** MetaTrader5 is not installable in the test environment, so the test file injects a fake `MetaTrader5` module into `sys.modules` before importing the module under test.  Any future test for this file must follow the same pattern.

**How to apply:** When adding tests for any file that imports `MetaTrader5` at module level, inject the fake module via `sys.modules["MetaTrader5"] = _fake_mt5` before loading the module under test with `importlib.util.spec_from_file_location`.

`last_trading_bot_v2.0_pivot_zone_syncro/tests/test_risk_management.py` covers risk management logic in that subproject.
