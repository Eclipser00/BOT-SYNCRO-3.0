"""Tests for download_mt5_data.py.

MetaTrader5 is not available in the test environment (requires the MT5
platform to be installed).  A fake mt5 module is injected into sys.modules
before download_mt5_data is imported so that every reference to mt5.*
inside the module under test resolves to our controlled stub values.
"""

from __future__ import annotations

import json
import importlib
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Build a fake MetaTrader5 module that exposes the TIMEFRAME_* constants
# used by download_mt5_data.TIMEFRAME_MAP.
# ---------------------------------------------------------------------------
_FAKE_MT5_CONSTANTS = {
    "TIMEFRAME_M1": 1,
    "TIMEFRAME_M3": 3,
    "TIMEFRAME_M5": 5,
    "TIMEFRAME_M15": 15,
    "TIMEFRAME_M30": 30,
    "TIMEFRAME_H1": 16385,
    "TIMEFRAME_H4": 16388,
    "TIMEFRAME_D1": 16408,
    "TIMEFRAME_W1": 32769,
    "TIMEFRAME_MN1": 49153,
}

_fake_mt5 = types.ModuleType("MetaTrader5")
for _name, _value in _FAKE_MT5_CONSTANTS.items():
    setattr(_fake_mt5, _name, _value)

# Functions that download_mt5_data may call at runtime (not at import time)
_fake_mt5.initialize = MagicMock(return_value=True)
_fake_mt5.shutdown = MagicMock()
_fake_mt5.last_error = MagicMock(return_value=(0, ""))
_fake_mt5.symbol_info = MagicMock(return_value=None)
_fake_mt5.symbol_select = MagicMock(return_value=True)
_fake_mt5.symbol_info_tick = MagicMock(return_value=None)
_fake_mt5.copy_rates_range = MagicMock(return_value=None)
_fake_mt5.order_calc_margin = MagicMock(return_value=None)
_fake_mt5.ORDER_TYPE_BUY = 0

# Inject before the module is loaded so that `import MetaTrader5 as mt5`
# inside download_mt5_data resolves to our fake.
sys.modules["MetaTrader5"] = _fake_mt5

# Now import the module under test (after the fake is in sys.modules).
import importlib as _importlib  # noqa: E402

_MODULE_PATH = "backtest bot v7.0 syncro.download_mt5_data"

# The directory containing the package is not necessarily on sys.path.
# Insert it so the relative import works.
import os as _os  # noqa: E402

_pkg_parent = _os.path.dirname(_os.path.abspath(__file__))
_project_root = _os.path.dirname(_pkg_parent)
_sys_path_inserted = False
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
    _sys_path_inserted = True

# The subdirectory name contains spaces, so we use importlib.util directly.
import importlib.util as _util  # noqa: E402

_spec = _util.spec_from_file_location(
    "download_mt5_data",
    _os.path.join(_pkg_parent, "download_mt5_data.py"),
)
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Convenient aliases
TIMEFRAME_MAP = _mod.TIMEFRAME_MAP
validate_inputs = _mod.validate_inputs
parse_utc_datetime = _mod.parse_utc_datetime
normalize_tickers = _mod.normalize_tickers


# ===========================================================================
# Tests — TIMEFRAME_MAP contents
# ===========================================================================

class TestTimeframeMapContainsM3(unittest.TestCase):
    """Validates that M3 was added to TIMEFRAME_MAP."""

    def test_m3_key_present_in_timeframe_map(self):
        # M3 must exist as a key after the recent change.
        self.assertIn("M3", TIMEFRAME_MAP)

    def test_m3_value_is_not_none(self):
        # The value mapped to "M3" must be a non-None integer.
        self.assertIsNotNone(TIMEFRAME_MAP.get("M3"))

    def test_m3_value_matches_fake_constant(self):
        # The value must equal the TIMEFRAME_M3 constant exposed by mt5.
        self.assertEqual(TIMEFRAME_MAP["M3"], _FAKE_MT5_CONSTANTS["TIMEFRAME_M3"])


class TestTimeframeMapPreExistingEntries(unittest.TestCase):
    """Validates that adding M3 did not break the pre-existing timeframes."""

    EXPECTED_KEYS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]

    def test_all_original_keys_present(self):
        # Every key that existed before the M3 addition must still be present.
        for key in self.EXPECTED_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, TIMEFRAME_MAP)

    def test_all_original_values_not_none(self):
        # None of the original values should have been corrupted.
        for key in self.EXPECTED_KEYS:
            with self.subTest(key=key):
                self.assertIsNotNone(TIMEFRAME_MAP[key])

    def test_all_original_values_match_constants(self):
        # Each value must match the corresponding fake constant.
        mapping = {
            "M1": "TIMEFRAME_M1",
            "M5": "TIMEFRAME_M5",
            "M15": "TIMEFRAME_M15",
            "M30": "TIMEFRAME_M30",
            "H1": "TIMEFRAME_H1",
            "H4": "TIMEFRAME_H4",
            "D1": "TIMEFRAME_D1",
            "W1": "TIMEFRAME_W1",
            "MN1": "TIMEFRAME_MN1",
        }
        for tf_key, const_name in mapping.items():
            with self.subTest(tf_key=tf_key):
                self.assertEqual(
                    TIMEFRAME_MAP[tf_key],
                    _FAKE_MT5_CONSTANTS[const_name],
                )

    def test_timeframe_map_total_count(self):
        # After adding M3 the map must contain exactly 10 entries.
        self.assertEqual(len(TIMEFRAME_MAP), 10)


# ===========================================================================
# Tests — TIMEFRAME toggle comment (source-level check)
# ===========================================================================

class TestTimeframeToggleComment(unittest.TestCase):
    """Validates that the TIMEFRAME toggle comment mentions M3."""

    def test_toggle_comment_contains_m3(self):
        # Read the source file and verify M3 appears in the TIMEFRAME line comment.
        source_path = _os.path.join(_os.path.dirname(__file__), "download_mt5_data.py")
        with open(source_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("TIMEFRAME"):
                    # The comment after the value must include M3.
                    self.assertIn("M3", line, msg=f"M3 not found in line: {line!r}")
                    return
        self.fail("TIMEFRAME toggle line not found in source file.")


# ===========================================================================
# Tests — validate_inputs() accepts M3
# ===========================================================================

class TestValidateInputsAcceptsM3(unittest.TestCase):
    """Validates that validate_inputs() does not reject 'M3' as TIMEFRAME."""

    def _run_with_timeframe(self, tf: str):
        """Patch module-level globals and call validate_inputs()."""
        with (
            patch.object(_mod, "START_UTC", "2026-01-01 00:00:00"),
            patch.object(_mod, "END_UTC", "2026-01-02 00:00:00"),
            patch.object(_mod, "TIMEFRAME", tf),
            patch.object(_mod, "TICKERS", ["AAPL"]),
        ):
            return _mod.validate_inputs()

    def test_validate_inputs_accepts_m3(self):
        # validate_inputs() must return without raising when TIMEFRAME='M3'.
        start, end, tf, tickers = self._run_with_timeframe("M3")
        self.assertEqual(tf, "M3")

    def test_validate_inputs_m3_returns_correct_timeframe_string(self):
        # The returned timeframe string must be exactly 'M3'.
        _, _, tf, _ = self._run_with_timeframe("M3")
        self.assertEqual(tf, "M3")

    def test_validate_inputs_rejects_invalid_timeframe(self):
        # An unknown timeframe must still raise ValueError.
        with self.assertRaises(ValueError):
            self._run_with_timeframe("M2")

    def test_validate_inputs_accepts_m1(self):
        # M1 (pre-existing) must still be accepted.
        _, _, tf, _ = self._run_with_timeframe("M1")
        self.assertEqual(tf, "M1")

    def test_validate_inputs_accepts_m5(self):
        # M5 (pre-existing) must still be accepted.
        _, _, tf, _ = self._run_with_timeframe("M5")
        self.assertEqual(tf, "M5")

    def test_validate_inputs_timeframe_normalized_to_uppercase(self):
        # Lowercase 'm3' should be normalised to 'M3' without error.
        _, _, tf, _ = self._run_with_timeframe("m3")
        self.assertEqual(tf, "M3")


# ===========================================================================
# Tests — parse_utc_datetime (pure helper, no mt5 dependency)
# ===========================================================================

class TestParseUtcDatetime(unittest.TestCase):
    """Validates the UTC datetime parser used internally by validate_inputs."""

    def test_valid_datetime_parses_correctly(self):
        # Happy-path: a well-formed string must be parsed without error.
        from datetime import timezone
        dt = parse_utc_datetime("2026-01-15 08:30:00", "TEST")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_invalid_datetime_raises_value_error(self):
        # A malformed string must raise ValueError.
        with self.assertRaises(ValueError):
            parse_utc_datetime("not-a-date", "TEST")

    def test_wrong_format_raises_value_error(self):
        # ISO format with 'T' separator is not accepted.
        with self.assertRaises(ValueError):
            parse_utc_datetime("2026-01-15T08:30:00", "TEST")


# ===========================================================================
# Tests — normalize_tickers (pure helper)
# ===========================================================================

class TestNormalizeTickers(unittest.TestCase):
    """Validates ticker normalisation logic."""

    def test_uppercase_conversion(self):
        # All tickers must be converted to uppercase.
        self.assertEqual(normalize_tickers(["aapl", "msft"]), ["AAPL", "MSFT"])

    def test_whitespace_stripped(self):
        # Leading/trailing whitespace must be removed.
        self.assertEqual(normalize_tickers(["  NVDA  "]), ["NVDA"])

    def test_duplicates_removed(self):
        # Duplicate tickers (after normalisation) must appear only once.
        result = normalize_tickers(["AAPL", "aapl", "AAPL"])
        self.assertEqual(result, ["AAPL"])

    def test_empty_strings_skipped(self):
        # Empty strings (after strip) must not appear in the output.
        result = normalize_tickers(["AAPL", "", "   ", "MSFT"])
        self.assertEqual(result, ["AAPL", "MSFT"])

    def test_empty_list_returns_empty(self):
        # An empty input must return an empty list.
        self.assertEqual(normalize_tickers([]), [])


# ===========================================================================
# Tests â€” instrument_specs.json synchronisation helpers
# ===========================================================================

class TestInstrumentSpecsHelpers(unittest.TestCase):
    """Validates MT5 symbol specs extraction and JSON overwrite behaviour."""

    def setUp(self):
        _fake_mt5.symbol_info.reset_mock()
        _fake_mt5.symbol_info_tick.reset_mock()
        _fake_mt5.order_calc_margin.reset_mock()

    def _symbol_info(self, margin_initial=999.0):
        return types.SimpleNamespace(
            trade_tick_size=0.01,
            trade_tick_value=1.25,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=50.0,
            margin_initial=margin_initial,
        )

    def test_latest_available_price_prefers_last(self):
        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=155.2,
            ask=155.3,
            bid=155.1,
        )

        self.assertEqual(_mod.latest_available_price("XOM"), 155.2)

    def test_latest_available_price_falls_back_to_ask_then_bid(self):
        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=0.0,
            ask=155.3,
            bid=155.1,
        )
        self.assertEqual(_mod.latest_available_price("XOM"), 155.3)

        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=0.0,
            ask=0.0,
            bid=155.1,
        )
        self.assertEqual(_mod.latest_available_price("XOM"), 155.1)

    def test_build_symbol_specs_uses_order_calc_margin(self):
        _fake_mt5.symbol_info.return_value = self._symbol_info()
        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=155.2,
            ask=155.3,
            bid=155.1,
        )
        _fake_mt5.order_calc_margin.return_value = 1234.5

        specs = _mod.build_symbol_specs("XOM")

        self.assertEqual(
            specs,
            {
                "trade_tick_size": 0.01,
                "trade_tick_value": 1.25,
                "trade_contract_size": 100.0,
                "volume_min": 0.01,
                "volume_step": 0.01,
                "volume_max": 50.0,
                "margin_per_lot": 1234.5,
            },
        )
        _fake_mt5.order_calc_margin.assert_called_once_with(
            _fake_mt5.ORDER_TYPE_BUY,
            "XOM",
            1.0,
            155.2,
        )

    def test_build_symbol_specs_falls_back_to_margin_initial(self):
        _fake_mt5.symbol_info.return_value = self._symbol_info(margin_initial=777.0)
        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=0.0,
            ask=155.3,
            bid=155.1,
        )
        _fake_mt5.order_calc_margin.return_value = None

        specs = _mod.build_symbol_specs("XOM")

        self.assertEqual(specs["margin_per_lot"], 777.0)
        _fake_mt5.order_calc_margin.assert_called_once_with(
            _fake_mt5.ORDER_TYPE_BUY,
            "XOM",
            1.0,
            155.3,
        )

    def test_build_symbol_specs_omits_margin_with_explicit_warning(self):
        _fake_mt5.symbol_info.return_value = self._symbol_info(margin_initial=None)
        _fake_mt5.symbol_info_tick.return_value = types.SimpleNamespace(
            last=0.0,
            ask=0.0,
            bid=0.0,
        )

        with patch.object(_mod, "log") as log_mock:
            specs = _mod.build_symbol_specs("XOM")

        self.assertNotIn("margin_per_lot", specs)
        logged = "\n".join(str(call.args[0]) for call in log_mock.call_args_list)
        self.assertIn("no hay ultimo precio disponible", logged)
        self.assertIn("margin_per_lot omitido", logged)

    def test_write_instrument_specs_overwrites_existing_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            specs_path = _os.path.join(temp_dir, "instrument_specs.json")
            with open(specs_path, "w", encoding="utf-8") as fh:
                json.dump({"EURUSD": {"trade_tick_size": 0.0001}}, fh)

            _mod.write_instrument_specs(
                {"JPM": {"trade_tick_size": 0.01}},
                specs_path=_mod.Path(specs_path),
            )

            with open(specs_path, encoding="utf-8") as fh:
                saved = json.load(fh)

        self.assertEqual(saved, {"JPM": {"trade_tick_size": 0.01}})


if __name__ == "__main__":
    unittest.main()
