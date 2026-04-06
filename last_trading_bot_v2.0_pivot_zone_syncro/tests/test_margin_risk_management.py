"""Tests de gestión de riesgo de margen.

Evalúa que el bot no abra posiciones cuando el margen usado supera los límites
configurados, evitando margin calls.
"""
from tests.conftest import BaseFakeBroker, DummyStrategy

from bot_trading.application.engine.bot_engine import TradingBot
from bot_trading.application.engine.order_executor import OrderExecutor
from bot_trading.application.risk_management import RiskManager
from bot_trading.domain.entities import (
    AccountInfo, OrderResult, SymbolConfig, RiskLimits, Position,
)


class FakeBrokerWithMargin(BaseFakeBroker):
    """Broker simulado con información de margen configurable."""

    def __init__(self, initial_balance: float = 10000.0) -> None:
        super().__init__()
        self.open_positions: list[Position] = []
        self.margin_per_lot = 100.0
        self.account_info = AccountInfo(
            balance=initial_balance,
            equity=initial_balance,
            margin=0.0,
            margin_free=initial_balance,
            margin_level=None,
        )

    def send_market_order(self, order_request) -> OrderResult:
        result = super().send_market_order(order_request)
        if order_request.order_type in {"BUY", "SELL"}:
            margin_required = order_request.volume * self.margin_per_lot
            position = Position(
                symbol=order_request.symbol,
                volume=order_request.volume,
                entry_price=1.0,
                stop_loss=order_request.stop_loss,
                take_profit=order_request.take_profit,
                strategy_name=order_request.comment or "unknown",
                open_time=self._current_time,
                magic_number=order_request.magic_number,
            )
            self.open_positions.append(position)
            self.account_info.margin += margin_required
            self.account_info.margin_free = self.account_info.equity - self.account_info.margin
            if self.account_info.equity > 0:
                self.account_info.margin_level = (
                    (self.account_info.equity / self.account_info.margin) * 100
                    if self.account_info.margin > 0 else None
                )
        return result

    def get_open_positions(self):
        return self.open_positions.copy()

    def get_account_info(self) -> AccountInfo:
        return self.account_info

    def set_account_info(self, balance: float, equity: float, margin: float) -> None:
        self.account_info.balance = balance
        self.account_info.equity = equity
        self.account_info.margin = margin
        self.account_info.margin_free = equity - margin
        if equity > 0:
            self.account_info.margin_level = (equity / margin) * 100 if margin > 0 else None


def test_risk_manager_bloquea_orden_cuando_margen_supera_80_porciento() -> None:
    """Verifica que el risk manager bloquea Ã³rdenes cuando el margen usado supera el 80%.
    
    Escenario:
    - Balance inicial: 10000
    - LÃ­mite de margen: 80%
    - Margen usado actual: 8500 (85% del capital)
    - Nueva orden requiere: 100 de margen adicional
    - Resultado esperado: Orden BLOQUEADA
    """
    # Este test fallarÃ¡ inicialmente porque aÃºn no implementamos la validaciÃ³n de margen
    # Es parte del enfoque TDD: escribir el test primero
    
    broker = FakeBrokerWithMargin(initial_balance=10000.0)
    
    # Configurar cuenta con margen usado al 85% (8500 de 10000)
    broker.set_account_info(
        balance=10000.0,
        equity=10000.0,
        margin=8500.0  # 85% del capital usado
    )
    
    # Configurar lÃ­mite de margen al 80%
    risk_manager = RiskManager(
        RiskLimits(
            dd_global=None,
            initial_balance=10000.0,
            max_margin_usage_percent=80.0,
        )
    )
    
    # Verificar que el margen usado (85%) supera el lÃ­mite (80%)
    account_info = broker.get_account_info()
    margin_usage_percent = (account_info.margin / account_info.equity) * 100 if account_info.equity > 0 else 0
    
    assert margin_usage_percent > 80.0, "El margen usado debe superar el 80% para este test"
    
    # Verificar que el risk manager bloquea la orden
    result = risk_manager.check_margin_limits(account_info)
    assert result is False, "El risk manager debe bloquear cuando el margen supera el 80%"


def test_risk_manager_permite_orden_cuando_margen_esta_por_debajo_del_limite() -> None:
    """Verifica que el risk manager permite Ã³rdenes cuando el margen usado estÃ¡ por debajo del lÃ­mite.
    
    Escenario:
    - Balance inicial: 10000
    - LÃ­mite de margen: 80%
    - Margen usado actual: 5000 (50% del capital)
    - Nueva orden requiere: 100 de margen adicional
    - Resultado esperado: Orden PERMITIDA
    """
    broker = FakeBrokerWithMargin(initial_balance=10000.0)
    
    # Configurar cuenta con margen usado al 50% (5000 de 10000)
    broker.set_account_info(
        balance=10000.0,
        equity=10000.0,
        margin=5000.0  # 50% del capital usado
    )
    
    # Configurar lÃ­mite de margen al 80%
    risk_manager = RiskManager(
        RiskLimits(
            dd_global=None,
            initial_balance=10000.0,
            max_margin_usage_percent=80.0,
        )
    )
    
    # Verificar que el margen usado (50%) estÃ¡ por debajo del lÃ­mite (80%)
    account_info = broker.get_account_info()
    margin_usage_percent = (account_info.margin / account_info.equity) * 100 if account_info.equity > 0 else 0
    
    assert margin_usage_percent < 80.0, "El margen usado debe estar por debajo del 80% para este test"
    
    # Verificar que el risk manager permite la orden
    result = risk_manager.check_margin_limits(account_info)
    assert result is True, "El risk manager debe permitir cuando el margen estÃ¡ por debajo del 80%"


def test_risk_manager_bloquea_orden_cuando_margen_libre_insuficiente() -> None:
    """Verifica que el risk manager bloquea Ã³rdenes cuando no hay margen libre suficiente.
    
    Escenario:
    - Balance inicial: 10000
    - Equity: 10000
    - Margen usado: 9500
    - Margen libre: 500
    - Nueva orden requiere: 1000 de margen adicional
    - Resultado esperado: Orden BLOQUEADA (margen libre insuficiente)
    """
    broker = FakeBrokerWithMargin(initial_balance=10000.0)
    
    # Configurar cuenta con poco margen libre
    broker.set_account_info(
        balance=10000.0,
        equity=10000.0,
        margin=9500.0  # 95% del capital usado, solo 500 libre
    )
    
    account_info = broker.get_account_info()
    
    # Configurar risk manager con lÃ­mite de margen al 80%
    risk_manager = RiskManager(
        RiskLimits(
            dd_global=None,
            initial_balance=10000.0,
            max_margin_usage_percent=80.0,
        )
    )
    
    # Simular orden que requiere 1000 de margen (mÃ¡s de lo disponible)
    order_margin_required = 1000.0
    
    assert account_info.margin_free < order_margin_required, \
        "El margen libre debe ser insuficiente para esta orden"
    
    # Verificar que el risk manager bloquea la orden por falta de margen libre
    result = risk_manager.check_margin_limits(account_info, order_margin_required)
    assert result is False, "El risk manager debe bloquear cuando no hay margen libre suficiente"

