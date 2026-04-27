"""Tests de wiring de timeframes configurables."""

import config


def test_pivot_timeframe_toggles_drive_symbols_strategy_loop_and_csv() -> None:
    cfg = config.load_settings("production")
    config.validate_config(cfg)

    entry_tf = f"M{config.PIVOT_TF_ENTRY_MINUTES}"
    zone_tf = f"M{config.PIVOT_TF_ZONE_MINUTES}"
    stop_tf = f"M{config.PIVOT_TF_STOP_MINUTES}"
    expected_timeframes = list(dict.fromkeys([entry_tf, zone_tf, stop_tf]))

    assert {symbol.min_timeframe for symbol in cfg.symbols} == {entry_tf}
    assert cfg.loop.timeframe_minutes == config.PIVOT_TF_ENTRY_MINUTES
    assert cfg.data.csv_base_timeframe == entry_tf

    strategy = cfg.strategies[0]
    assert strategy.tf_entry == entry_tf
    assert strategy.tf_zone == zone_tf
    assert strategy.tf_stop == stop_tf
    assert strategy.timeframes == expected_timeframes
