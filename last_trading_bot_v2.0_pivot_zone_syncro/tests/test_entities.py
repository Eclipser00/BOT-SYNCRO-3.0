"""Tests de entidades de dominio."""
from datetime import datetime

from bot_trading.domain.entities import Position, SymbolConfig


def test_symbol_config_attributes_definidos() -> None:
    """Valida que SymbolConfig expone todos los atributos esperados."""
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1", n1=10, n2=5, n3=3)

    assert symbol.name == "EURUSD"
    assert symbol.min_timeframe == "M1"
    assert symbol.n1 == 10
    assert symbol.n2 == 5
    assert symbol.n3 == 3


def test_symbol_config_opcionales_son_none_por_defecto() -> None:
    """Valida que n1, n2, n3 son None cuando no se especifican."""
    symbol = SymbolConfig(name="GBPUSD", min_timeframe="M5")

    assert symbol.n1 is None
    assert symbol.n2 is None
    assert symbol.n3 is None


def test_position_crea_instancia_completa() -> None:
    """Verifica que todos los campos de Position se asignan correctamente."""
    now = datetime.utcnow()
    position = Position(
        symbol="EURUSD",
        volume=0.1,
        entry_price=1.1,
        stop_loss=1.0,
        take_profit=1.2,
        strategy_name="demo",
        open_time=now,
        magic_number=12345,
    )

    assert position.symbol == "EURUSD"
    assert position.volume == 0.1
    assert position.entry_price == 1.1
    assert position.stop_loss == 1.0
    assert position.take_profit == 1.2
    assert position.strategy_name == "demo"
    assert position.open_time == now
    assert position.magic_number == 12345


def test_position_magic_number_none_por_defecto() -> None:
    """Verifica que magic_number es None cuando no se especifica."""
    position = Position(
        symbol="EURUSD",
        volume=0.1,
        entry_price=1.1,
        stop_loss=1.0,
        take_profit=1.2,
        strategy_name="demo",
        open_time=datetime.utcnow(),
    )

    assert position.magic_number is None

