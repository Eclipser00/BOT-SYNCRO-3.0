"""Tests de bootstrap del autovisualizador en el entrypoint principal."""
from __future__ import annotations

from pathlib import Path

import bot_trading.main as main_mod
from config import load_settings
from bot_trading.domain.entities import SymbolConfig


def test_build_auto_visualizer_habilitado_por_defecto(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VISUALIZER_AUTO_ENABLE", raising=False)
    monkeypatch.setenv("VISUALIZER_REFRESH_SECONDS", "17")
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)

    captured: dict = {}

    class DummyAutoVisualizerService:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(main_mod, "AutoVisualizerService", DummyAutoVisualizerService)
    broker = type(
        "BrokerWithSnapshot",
        (),
        {"get_closed_trades_snapshot": lambda self, from_utc, to_utc: []},
    )()

    result = main_mod._build_auto_visualizer([SymbolConfig(name="EURUSD", min_timeframe="M1")], broker=broker)

    assert isinstance(result, DummyAutoVisualizerService)
    assert captured["refresh_seconds"] == 17
    assert captured["start_from_end"] is main_mod.settings.logging.visualizer_start_from_end
    assert callable(captured["closed_trades_provider"])
    assert captured["closed_trades_lookback_days"] == main_mod.settings.data.bootstrap_lookback_days_zone
    assert captured["symbols"][0].name == "EURUSD"
    assert captured["output_dir"] == tmp_path / "plots"
    assert captured["bot_events_path"] == tmp_path / "plots" / "bot_events.jsonl"


def test_build_auto_visualizer_se_puede_desactivar_por_env(monkeypatch) -> None:
    monkeypatch.setenv("VISUALIZER_AUTO_ENABLE", "0")

    result = main_mod._build_auto_visualizer([SymbolConfig(name="EURUSD", min_timeframe="M1")])

    assert result is None


def test_clean_plots_limpia_html_y_eventos_pero_conserva_cursor(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main_mod, "ROOT", tmp_path)
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    (plots_dir / "visualizerEURUSD.html").write_text("<html></html>", encoding="utf-8")
    (plots_dir / "bot_events.jsonl").write_text('{"event_type":"signal"}\n', encoding="utf-8")
    cursor_path = plots_dir / "closed_trades_cursor.json"
    cursor_path.write_text('{"cursor_ticket": 123}', encoding="utf-8")
    ledger_path = plots_dir / "closed_trades_ledger.jsonl"
    ledger_path.write_text('{"trade_key":"abc"}\n', encoding="utf-8")

    main_mod._clean_plots()

    assert not (plots_dir / "visualizerEURUSD.html").exists()
    assert (plots_dir / "bot_events.jsonl").read_text(encoding="utf-8") == ""
    assert cursor_path.read_text(encoding="utf-8") == '{"cursor_ticket": 123}'
    assert ledger_path.read_text(encoding="utf-8") == '{"trade_key":"abc"}\n'


def test_build_broker_pasa_config_temporal_de_sincronizacion(monkeypatch) -> None:
    cfg = load_settings("production")
    cfg.temporal.clock_sync_reference_symbols = ["EURUSD", "GBPUSD", "USDJPY", "EURGBP"]
    cfg.temporal.clock_sync_max_tick_age_seconds = 77
    monkeypatch.setattr(main_mod, "settings", cfg)

    captured: dict = {}

    class DummyMetaTrader5Client:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def connect(self) -> None:
            captured["connected"] = True

    monkeypatch.setattr(main_mod, "MetaTrader5Client", DummyMetaTrader5Client)

    result = main_mod._build_broker()

    assert isinstance(result, DummyMetaTrader5Client)
    assert captured["clock_sync_reference_symbols"] == ["EURUSD", "GBPUSD", "USDJPY", "EURGBP"]
    assert captured["clock_sync_max_tick_age_seconds"] == 77
    assert captured["connected"] is True
