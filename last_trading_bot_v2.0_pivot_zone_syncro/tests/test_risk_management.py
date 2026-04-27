"""Tests de la capa de gestion de riesgo."""
from datetime import datetime, timedelta, timezone

from bot_trading.application.risk_management import RiskManager
from bot_trading.domain.entities import Position, RiskLimits, TradeRecord


def _build_trade(symbol: str, strategy: str, pnl: float) -> TradeRecord:
    now = datetime.now(timezone.utc)
    return TradeRecord(
        symbol=symbol,
        strategy_name=strategy,
        entry_time=now - timedelta(minutes=5),
        exit_time=now,
        entry_price=1.0,
        exit_price=1.0,
        size=1.0,
        pnl=pnl,
        stop_loss=None,
        take_profit=None,
    )


def _build_position(symbol: str, strategy: str, profit: float) -> Position:
    now = datetime.now(timezone.utc)
    return Position(
        symbol=symbol,
        volume=1.0,
        entry_price=1.0,
        stop_loss=None,
        take_profit=None,
        strategy_name=strategy,
        open_time=now,
        profit=profit,
    )


def test_risk_manager_bloquea_bot_cuando_dd_global_superado() -> None:
    trades = [
        _build_trade("EURUSD", "strat", 1000.0),
        _build_trade("EURUSD", "strat", -600.0),
    ]
    manager = RiskManager(RiskLimits(dd_global=50.0, initial_balance=100.0))

    assert manager.check_bot_risk_limits(trades) is False


def test_risk_manager_bloquea_activo_cuando_dd_por_activo_superado() -> None:
    trades = [
        _build_trade("EURUSD", "strat", 500.0),
        _build_trade("EURUSD", "strat", -350.0),
    ]
    manager = RiskManager(RiskLimits(dd_por_activo={"EURUSD": 50.0}, initial_balance=100.0))

    assert manager.check_symbol_risk_limits("EURUSD", trades) is False


def test_risk_manager_bloquea_estrategia_cuando_dd_por_estrategia_superado() -> None:
    trades = [
        _build_trade("EURUSD", "trend", 1000.0),
        _build_trade("GBPUSD", "trend", 200.0),
        _build_trade("EURUSD", "trend", -900.0),
    ]
    manager = RiskManager(RiskLimits(dd_por_estrategia={"trend": 60.0}, initial_balance=100.0))

    assert manager.check_strategy_risk_limits("trend", trades) is False


def test_risk_manager_permite_operar_dentro_de_limites() -> None:
    trades = [
        _build_trade("EURUSD", "strat", 1000.0),
        _build_trade("EURUSD", "strat", -300.0),
    ]
    manager = RiskManager(RiskLimits(dd_global=50.0, initial_balance=100.0))

    assert manager.check_bot_risk_limits(trades) is True


def test_risk_manager_drawdown_sin_trades() -> None:
    manager = RiskManager(RiskLimits(dd_global=10.0, initial_balance=100.0))

    assert manager.check_bot_risk_limits([]) is True


def test_risk_manager_bloquea_por_pnl_flotante_abierto() -> None:
    manager = RiskManager(RiskLimits(dd_global=30.0, initial_balance=100000.0))
    open_positions = [_build_position("EURUSD", "PivotZoneTest", -31000.0)]

    assert manager.check_bot_risk_limits([], open_positions) is False


def test_risk_manager_normaliza_sufijo_timeframe_en_estrategia() -> None:
    manager = RiskManager(
        RiskLimits(
            dd_por_estrategia={"PivotZoneTest": 30.0},
            initial_balance=100000.0,
        )
    )
    trades = [_build_trade("EURUSD", "PivotZoneTest-M3", -31000.0)]
    open_positions = [_build_position("EURUSD", "PivotZoneTest-M3", 0.0)]

    assert manager.check_strategy_risk_limits("PivotZoneTest", trades, open_positions) is False
