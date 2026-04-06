"""Configuración global de pytest para el proyecto de trading bot.

Inyecta un mock de MetaTrader5 en sys.modules ANTES de que cualquier
módulo del proyecto intente importar la librería real. Esto permite
ejecutar tests sin tener MT5 instalado ni un terminal corriendo.
"""
import sys
from unittest.mock import MagicMock
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from bot_trading.domain.entities import OrderResult, TradeRecord, Position
from bot_trading.application.engine.signals import Signal, SignalType

# ============================================
# MOCK DE METATRADER5 A NIVEL DE MÓDULO
# Se inyecta antes de cualquier import para
# que mt5_client.py reciba este mock en lugar
# de la librería real.
# ============================================
mt5_mock = MagicMock()

# -- Constantes de timeframe (valores reales de MT5) --
mt5_mock.TIMEFRAME_M1 = 1
mt5_mock.TIMEFRAME_M3 = 3
mt5_mock.TIMEFRAME_M5 = 5
mt5_mock.TIMEFRAME_M15 = 15
mt5_mock.TIMEFRAME_M30 = 30
mt5_mock.TIMEFRAME_H1 = 16385
mt5_mock.TIMEFRAME_H4 = 16388
mt5_mock.TIMEFRAME_D1 = 16408
mt5_mock.TIMEFRAME_W1 = 32769
mt5_mock.TIMEFRAME_MN1 = 49153

# -- Constantes de tipo de orden --
mt5_mock.ORDER_TYPE_BUY = 0
mt5_mock.ORDER_TYPE_SELL = 1

# -- Constantes de tipo de posición --
mt5_mock.POSITION_TYPE_BUY = 0
mt5_mock.POSITION_TYPE_SELL = 1

# -- Constantes de acción de trade --
mt5_mock.TRADE_ACTION_DEAL = 1
mt5_mock.TRADE_ACTION_SLTP = 6
mt5_mock.TRADE_ACTION_PENDING = 5
mt5_mock.TRADE_ACTION_MODIFY = 7
mt5_mock.TRADE_ACTION_REMOVE = 8

# -- Constantes de filling mode --
mt5_mock.ORDER_FILLING_FOK = 0
mt5_mock.ORDER_FILLING_IOC = 1
mt5_mock.ORDER_FILLING_RETURN = 2

# -- Constantes de tiempo de orden --
mt5_mock.ORDER_TIME_GTC = 0

# -- Constantes de retcode --
mt5_mock.TRADE_RETCODE_DONE = 10009

# -- Constantes de deal entry --
mt5_mock.DEAL_ENTRY_IN = 0
mt5_mock.DEAL_ENTRY_OUT = 1

# Inyectar el mock en sys.modules para interceptar `import MetaTrader5`
sys.modules['MetaTrader5'] = mt5_mock


# ============================================
# BROKER BASE COMPARTIDO
# Evita duplicación entre test_margin_risk_management
# y test_risk_management_integration
# ============================================

class BaseFakeBroker:
    """Broker falso base con comportamiento común a todos los tests de integración."""

    def __init__(self) -> None:
        self.orders_sent: list = []
        self.closed_trades: list[TradeRecord] = []
        self._current_time = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)

    def connect(self) -> None:
        return None

    def get_ohlcv(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        index = pd.date_range(start=start, end=end, freq="1min")
        data = {
            "open": [1.0] * len(index),
            "high": [1.0] * len(index),
            "low": [1.0] * len(index),
            "close": [1.0] * len(index),
            "volume": [1] * len(index),
        }
        df = pd.DataFrame(data, index=index)
        df.attrs["symbol"] = symbol
        return df

    def send_market_order(self, order_request) -> OrderResult:
        self.orders_sent.append(order_request)
        return OrderResult(success=True, order_id=len(self.orders_sent))

    def get_closed_trades(self) -> list[TradeRecord]:
        return self.closed_trades.copy()


# ============================================
# DUMMY STRATEGY COMPARTIDA
# ============================================

class DummyStrategy:
    """Estrategia que siempre emite una señal de compra. Compartida entre tests."""

    def __init__(self, name: str, symbols: list[str] | None = None):
        self.name = name
        self.timeframes = ["M1"]
        self.allowed_symbols = symbols

    def generate_signals(self, data_by_timeframe):
        signals = []
        for symbol in (self.allowed_symbols or ["EURUSD"]):
            signals.append(
                Signal(
                    symbol=symbol,
                    strategy_name=self.name,
                    timeframe="M1",
                    signal_type=SignalType.BUY,
                    size=0.01,
                    stop_loss=None,
                    take_profit=None,
                )
            )
        return signals
