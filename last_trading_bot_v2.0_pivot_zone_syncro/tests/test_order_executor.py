"""Tests del ejecutor de órdenes."""
from datetime import datetime, timezone

from bot_trading.application.engine.order_executor import OrderExecutor
from bot_trading.domain.entities import OrderRequest, OrderResult, Position


class FakeBroker:
    """Broker simulado que almacena la última orden enviada."""

    def __init__(self) -> None:
        self.last_order: OrderRequest | None = None

    def send_market_order(self, order_request: OrderRequest) -> OrderResult:
        self.last_order = order_request
        return OrderResult(success=True, order_id=1)

    def get_open_positions(self):
        return []


class FakeBrokerWithPositions:
    """Broker que devuelve posiciones configurables."""

    def __init__(self, positions=None):
        self.positions = positions or []

    def send_market_order(self, order_request):
        return OrderResult(success=True, order_id=1)

    def get_open_positions(self):
        return self.positions


class FakeBrokerRejected:
    """Broker que siempre rechaza órdenes."""

    def send_market_order(self, order_request):
        return OrderResult(success=False, error_message="rejected")

    def get_open_positions(self):
        return []


class ExecutorSpy(OrderExecutor):
    """OrderExecutor que captura eventos emitidos en lugar de escribir a disco."""

    def __init__(self, broker_client):
        super().__init__(broker_client)
        self.events: list[dict] = []

    def _emit_event(self, payload: dict) -> None:
        self.events.append(payload)


def _make_position(symbol: str, magic_number: int | None = None) -> Position:
    """Crea una Position de prueba con valores por defecto."""
    return Position(
        symbol=symbol,
        volume=0.1,
        entry_price=1.1,
        stop_loss=None,
        take_profit=None,
        strategy_name="test",
        open_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        magic_number=magic_number,
    )


def test_order_executor_envia_orden_y_interpreta_respuesta() -> None:
    """El ejecutor debe enviar la orden y retornar el resultado del broker."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)
    request = OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY")

    result = executor.execute_order(request)

    assert broker.last_order == request
    assert result.success is True
    assert result.order_id == 1


def test_order_executor_eventos_fill_y_position_usan_fill_price_real() -> None:
    class BrokerConFill:
        def send_market_order(self, order_request: OrderRequest) -> OrderResult:
            return OrderResult(success=True, order_id=7, fill_price=1.23456)

        def get_open_positions(self):
            return []

    class ExecutorSpy(OrderExecutor):
        def __init__(self, broker_client) -> None:
            super().__init__(broker_client)
            self.events: list[dict] = []

        def _emit_event(self, payload: dict) -> None:  # type: ignore[override]
            self.events.append(payload)

    broker = BrokerConFill()
    executor = ExecutorSpy(broker)
    request = OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", timeframe="M1")

    result = executor.execute_order(request)

    assert result.success is True
    fill_events = [e for e in executor.events if e.get("event_type") == "order_fill"]
    position_events = [e for e in executor.events if e.get("event_type") == "position"]
    assert fill_events
    assert position_events
    assert float(fill_events[-1]["price"]) == 1.23456
    assert float(position_events[-1]["price"]) == 1.23456


def test_order_executor_normaliza_ts_event_naive_a_utc() -> None:
    class BrokerConFill:
        def send_market_order(self, order_request: OrderRequest) -> OrderResult:
            return OrderResult(success=True, order_id=11, fill_price=1.2000)

        def get_open_positions(self):
            return []

    class ExecutorSpy(OrderExecutor):
        def __init__(self, broker_client) -> None:
            super().__init__(broker_client)
            self.events: list[dict] = []

        def _emit_event(self, payload: dict) -> None:  # type: ignore[override]
            self.events.append(payload)

    broker = BrokerConFill()
    executor = ExecutorSpy(broker)
    request = OrderRequest(
        symbol="EURUSD",
        volume=0.01,
        order_type="BUY",
        timeframe="M1",
        ts_event="2026-03-05T06:29:37",
    )

    result = executor.execute_order(request)

    assert result.success is True
    assert executor.events
    for event in executor.events:
        assert event["ts_event"].endswith("+00:00")


# ============================================
# TESTS DE REGISTRO DE POSICIONES
# Verifican que execute_order mantiene el dict
# open_positions sincronizado con las órdenes
# ============================================


def test_execute_order_registra_posicion_en_open_positions() -> None:
    """Una orden BUY exitosa debe registrar exactamente 1 posición."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)
    request = OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=99)

    executor.execute_order(request)

    assert len(executor.open_positions) == 1
    assert "EURUSD_99" in executor.open_positions
    pos = executor.open_positions["EURUSD_99"]
    assert pos.symbol == "EURUSD"
    assert pos.magic_number == 99


def test_execute_order_close_elimina_posicion_del_registro() -> None:
    """Una orden CLOSE debe eliminar la posición previamente registrada."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)

    # Abrir posición
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=99)
    )
    assert len(executor.open_positions) == 1

    # Cerrar posición
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="CLOSE", magic_number=99)
    )
    assert len(executor.open_positions) == 0


def test_execute_order_fallida_no_registra_posicion() -> None:
    """Si el broker rechaza la orden, no se debe registrar ninguna posición."""
    broker = FakeBrokerRejected()
    executor = OrderExecutor(broker)
    request = OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=1)

    result = executor.execute_order(request)

    assert result.success is False
    assert len(executor.open_positions) == 0


# ============================================
# TESTS DE SINCRONIZACIÓN CON BROKER
# Verifican que sync_state() reconstruye el
# estado local a partir de posiciones reales
# ============================================


def test_sync_state_reconstruye_posiciones_desde_broker() -> None:
    """sync_state debe poblar open_positions con las posiciones del broker."""
    positions = [
        _make_position("EURUSD", magic_number=1),
        _make_position("GBPUSD", magic_number=2),
    ]
    broker = FakeBrokerWithPositions(positions=positions)
    executor = OrderExecutor(broker)

    executor.sync_state()

    assert len(executor.open_positions) == 2
    assert "EURUSD_1" in executor.open_positions
    assert "GBPUSD_2" in executor.open_positions


def test_sync_state_limpia_posiciones_obsoletas() -> None:
    """sync_state con lista vacía del broker debe limpiar posiciones locales."""
    broker = FakeBrokerWithPositions(positions=[])
    executor = OrderExecutor(broker)
    # Registrar manualmente una posición "fantasma"
    executor.open_positions["EURUSD_1"] = _make_position("EURUSD", magic_number=1)
    assert len(executor.open_positions) == 1

    executor.sync_state()

    assert len(executor.open_positions) == 0


# ============================================
# TESTS DE has_open_position
# Verifican búsqueda por magic_number y
# fallback por símbolo
# ============================================


def test_has_open_position_con_magic_number() -> None:
    """has_open_position filtra correctamente por magic_number."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=42)
    )

    assert executor.has_open_position("EURUSD", magic_number=42) is True
    assert executor.has_open_position("EURUSD", magic_number=99) is False


def test_has_open_position_fallback_por_symbol() -> None:
    """Sin magic_number, has_open_position busca por símbolo solamente."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY")
    )

    assert executor.has_open_position("EURUSD") is True
    assert executor.has_open_position("GBPUSD") is False


# ============================================
# TESTS DE EVENTOS
# Verifican que se emiten eventos correctos
# al abrir y cerrar posiciones
# ============================================


def test_close_emite_evento_position_flat() -> None:
    """Al cerrar una posición, se debe emitir un evento position con side=flat."""
    broker = FakeBroker()
    executor = ExecutorSpy(broker)

    # Abrir y cerrar
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=1)
    )
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="CLOSE", magic_number=1)
    )

    # Filtrar eventos de cierre de posición
    close_events = [
        e for e in executor.events
        if e.get("event_type") == "position" and e.get("reason") == "position_close"
    ]
    assert len(close_events) == 1
    assert close_events[0]["side"] == "flat"
    assert close_events[0]["size"] == 0.0


# ============================================
# TESTS DE _remove_position
# Verifican eliminación con y sin magic_number
# ============================================


def test_remove_position_sin_magic_elimina_todas_del_simbolo() -> None:
    """Sin magic_number, _remove_position elimina todas las posiciones del símbolo."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)
    # Registrar 2 posiciones de EURUSD con magic distintos
    executor.open_positions["EURUSD_10"] = _make_position("EURUSD", magic_number=10)
    executor.open_positions["EURUSD_20"] = _make_position("EURUSD", magic_number=20)
    assert len(executor.open_positions) == 2

    executor._remove_position("EURUSD", magic_number=None, emit_event=False)

    assert len(executor.open_positions) == 0


# ============================================
# TESTS DE MÚLTIPLES POSICIONES
# Verifican coexistencia de posiciones del
# mismo símbolo con distintos magic_number
# ============================================


def test_multiples_posiciones_mismo_simbolo_distintos_magic() -> None:
    """Dos BUY del mismo símbolo con magic distintos coexisten."""
    broker = FakeBroker()
    executor = OrderExecutor(broker)

    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=1)
    )
    executor.execute_order(
        OrderRequest(symbol="EURUSD", volume=0.01, order_type="BUY", magic_number=2)
    )

    assert len(executor.open_positions) == 2
    assert "EURUSD_1" in executor.open_positions
    assert "EURUSD_2" in executor.open_positions


# ============================================
# TESTS DE flush_pending_fills
# Verifican el procesamiento de fills
# pendientes asíncronos
# ============================================


def test_flush_pending_fills_procesa_fills_pendientes() -> None:
    """flush_pending_fills debe consumir fills y registrar posiciones."""

    class FillResult:
        """Simula el resultado de un fill del broker."""
        def __init__(self, order_id, price):
            self.order_id = order_id
            self.price = price

    class FakeBrokerWithFills:
        """Broker que devuelve fills pendientes una sola vez."""
        def __init__(self):
            self._fills = [FillResult(order_id=5, price=1.5)]

        def send_market_order(self, order_request):
            return OrderResult(success=True, order_id=5)

        def get_open_positions(self):
            return []

        def consume_filled_market_orders(self):
            fills = self._fills
            self._fills = []
            return fills

    broker = FakeBrokerWithFills()
    executor = OrderExecutor(broker)

    # Simular un fill pendiente registrado manualmente
    executor.pending_market_fills.append({
        "order_id": 5,
        "order_request": OrderRequest(
            symbol="EURUSD", volume=0.01, order_type="BUY"
        ),
    })

    executor.flush_pending_fills()

    # El fill fue procesado: la lista de pendientes está vacía
    assert len(executor.pending_market_fills) == 0
    # La posición fue registrada
    assert len(executor.open_positions) >= 1
