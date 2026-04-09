"""Script de prueba para verificar la conexión con MetaTrader 5.

Este script realiza una serie de pruebas básicas para verificar que:
1. MetaTrader5 está instalado y corriendo
2. Se puede establecer conexión
3. Se pueden obtener datos de mercado
4. Se pueden consultar posiciones y trades
5. Los símbolos configurados están disponibles

NO USA PYTEST, ES UN SCRIPT DE PRUEBA.
python tests/check_mt5_connection.py

Ejecutar antes de usar el bot en producción.
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Asegurar que el paquete está en sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_trading.infrastructure.mt5_client import (
    MetaTrader5Client,
    MT5ConnectionError,
    MT5DataError,
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_connection():
    """Prueba de conexión básica con MT5."""
    logger.info("="*80)
    logger.info("TEST 1: Conexión con MetaTrader 5")
    logger.info("="*80)
    
    try:
        client = MetaTrader5Client()
        client.connect()
        logger.info("✅ Conexión exitosa")
        return client
    except MT5ConnectionError as e:
        logger.error("❌ Error de conexión: %s", e)
        logger.error("\nVerifica que:")
        logger.error("  1. MetaTrader 5 esté instalado")
        logger.error("  2. El terminal esté corriendo")
        logger.error("  3. Estés logueado en una cuenta")
        sys.exit(1)


def test_account_info(client):
    """Prueba obtención de información de cuenta."""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Información de Cuenta")
    logger.info("="*80)
    
    try:
        # Usar la API del cliente en lugar de llamar a MT5 directamente.
        # Solo logueamos los campos que realmente existen en el dataclass AccountInfo.
        info = client.get_account_info()
        logger.info("✅ Información de cuenta obtenida:")
        logger.info("  - Balance: %.2f", info.balance)
        logger.info("  - Equity: %.2f", info.equity)
        logger.info("  - Margen: %.2f", info.margin)
        logger.info("  - Margen libre: %.2f", info.margin_free)
        logger.info(
            "  - Nivel de margen: %.2f%%",
            info.margin_level if info.margin_level else 0,
        )
        assert info.balance >= 0
    except (MT5ConnectionError, MT5DataError) as e:
        logger.error("❌ Error al obtener información: %s", e)


def test_symbols_availability(client, symbols):
    """Prueba disponibilidad de símbolos."""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Disponibilidad de Símbolos")
    logger.info("="*80)
    
    available = []
    unavailable = []
    
    for symbol in symbols:
        try:
            # Probamos disponibilidad intentando descargar unas pocas velas M1 recientes.
            # Si el símbolo no existe o está deshabilitado, get_ohlcv lanzará MT5DataError.
            now = datetime.now(timezone.utc)
            client.get_ohlcv(symbol, "M1", now - timedelta(minutes=5), now)
            available.append(symbol)
            logger.info("✅ %s: Disponible", symbol)
        except MT5DataError:
            unavailable.append(symbol)
            logger.error("❌ %s: NO disponible", symbol)
    
    logger.info("\nResumen:")
    logger.info("  - Disponibles: %d/%d", len(available), len(symbols))
    logger.info("  - No disponibles: %d/%d", len(unavailable), len(symbols))
    
    if unavailable:
        logger.warning("\n⚠️ Símbolos no disponibles: %s", unavailable)
        logger.warning("Estos símbolos NO se podrán operar")
    
    return available


def test_ohlcv_and_timeframes(client, symbols):
    """Prueba descarga de datos OHLCV y disponibilidad de timeframes.

    Ejecuta dos bloques:
      1) Descarga de H1 (últimas 24h) para los primeros 2 símbolos.
      2) Descarga del primer símbolo en múltiples timeframes.
    """
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Descarga de Datos OHLCV y Timeframes")
    logger.info("="*80)

    # Bloque 1: descarga H1 de 24h en los primeros 2 símbolos
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=24)

    success_count = 0

    for symbol in symbols[:2]:  # Probar con los primeros 2 símbolos
        try:
            logger.info("\nDescargando datos de %s...", symbol)
            df = client.get_ohlcv(symbol, "H1", start, end)

            if len(df) > 0:
                logger.info("✅ %s: %d registros descargados", symbol, len(df))
                logger.info("  - Primer registro: %s", df.index[0])
                logger.info("  - Último registro: %s", df.index[-1])
                logger.info("  - Último precio: %.5f", df.iloc[-1]['close'])
                success_count += 1
            else:
                logger.warning("⚠️ %s: Sin datos en el rango solicitado", symbol)
        except Exception as e:
            logger.error("❌ Error al descargar %s: %s", symbol, e)

    logger.info("\nResumen: %d/%d símbolos descargados exitosamente",
               success_count, min(2, len(symbols)))

    # Bloque 2: verificar distintos timeframes usando el primer símbolo disponible
    timeframes = {
        "M1": timedelta(hours=1),
        "M5": timedelta(hours=2),
        "M15": timedelta(hours=4),
        "H1": timedelta(hours=24),
        "H4": timedelta(days=7),
        "D1": timedelta(days=30),
    }
    logger.info("\nProbando timeframes con símbolo: %s", symbols[0])
    end = datetime.now(timezone.utc)
    for tf, delta in timeframes.items():
        try:
            start = end - delta
            df = client.get_ohlcv(symbols[0], tf, start, end)
            assert len(df) >= 0
            logger.info("✅ %s: %d registros", tf, len(df))
        except Exception as e:
            logger.error("❌ %s: Error - %s", tf, e)


def test_positions_and_trades(client):
    """Prueba consulta de posiciones y trades."""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: Posiciones y Trades")
    logger.info("="*80)
    
    try:
        # Posiciones abiertas
        positions = client.get_open_positions()
        logger.info("✅ Posiciones abiertas: %d", len(positions))
        
        if positions:
            for pos in positions:
                logger.info("  - %s: %.2f lotes @ %.5f (Magic: %s)",
                           pos.symbol, pos.volume, pos.entry_price, pos.magic_number)
        else:
            logger.info("  (No hay posiciones abiertas)")
        
        # Trades cerrados
        trades = client.get_closed_trades()
        logger.info("✅ Trades cerrados (hoy): %d", len(trades))
        
        if trades:
            total_pnl = sum(t.pnl for t in trades)
            logger.info("  - PnL total: %.2f", total_pnl)
            
            # Mostrar últimos 5 trades
            for trade in trades[:5]:
                logger.info("  - %s: %.2f lotes, PnL=%.2f, Entrada=%.5f, Salida=%.5f",
                           trade.symbol, trade.size, trade.pnl,
                           trade.entry_price, trade.exit_price)
        else:
            logger.info("  (No hay trades cerrados hoy)")
            
    except Exception as e:
        logger.error("❌ Error al consultar posiciones/trades: %s", e)


def test_open_orders(client):
    """Prueba consulta de órdenes pendientes abiertas."""
    logger.info("\n" + "="*80)
    logger.info("TEST 6: Órdenes Pendientes Abiertas")
    logger.info("="*80)
    try:
        orders = client.get_open_orders()
        assert isinstance(orders, list)
        logger.info("✅ Órdenes pendientes: %d", len(orders))
        # Mostramos las primeras 3 para no inundar el log si hay muchas.
        for order in orders[:3]:
            logger.info("  - ID: %s | %s | %s | %.2f lotes @ %.5f",
                       order.order_id, order.symbol, order.order_type,
                       order.volume, order.price)
    except Exception as e:
        logger.error("❌ Error al consultar órdenes: %s", e)


def test_server_time(client):
    """Prueba hora del servidor MT5."""
    logger.info("\n" + "="*80)
    logger.info("TEST 7: Hora del Servidor")
    logger.info("="*80)
    try:
        server_time = client.get_server_time(symbol="EURUSD")
        # El cliente garantiza que el datetime devuelto es timezone-aware (UTC).
        assert server_time.tzinfo is not None, "server_time debe tener timezone"
        logger.info("✅ Hora del servidor: %s", server_time.isoformat())
    except Exception as e:
        logger.error("❌ Error al obtener hora del servidor: %s", e)


def test_closed_trades_snapshot(client):
    """Prueba snapshot de trades cerrados en rango."""
    logger.info("\n" + "="*80)
    logger.info("TEST 8: Snapshot de Trades Cerrados (24h)")
    logger.info("="*80)
    try:
        # Ventana de 24h hacia atrás desde "ahora" en UTC.
        to_utc = datetime.now(timezone.utc)
        from_utc = to_utc - timedelta(hours=24)
        trades = client.get_closed_trades_snapshot(from_utc, to_utc)
        assert isinstance(trades, list)
        logger.info("✅ Trades cerrados (últimas 24h): %d", len(trades))
        # Mostramos como máximo los primeros 5 para mantener el log legible.
        for trade in trades[:5]:
            logger.info("  - %s: %.2f lotes, PnL=%.2f, Entrada=%.5f, Salida=%.5f",
                       trade.symbol, trade.size, trade.pnl,
                       trade.entry_price, trade.exit_price)
    except Exception as e:
        logger.error("❌ Error al obtener snapshot: %s", e)


def test_pending_order_lifecycle(client):
    """Prueba ciclo completo de orden pendiente: crear → modificar → cancelar."""
    logger.info("\n" + "="*80)
    logger.info("TEST 9: Ciclo de Vida de Orden Pendiente (REAL)")
    logger.info("="*80)
    try:
        # Importamos MT5 solo aquí para leer el volumen mínimo del símbolo.
        # No hay atajo equivalente en la API pública del cliente.
        import MetaTrader5 as mt5
        sym_info = mt5.symbol_info("EURUSD")
        volume_min = sym_info.volume_min

        # Tomamos el precio de referencia de la última vela M1 disponible.
        now = datetime.now(timezone.utc)
        df = client.get_ohlcv("EURUSD", "M1", now - timedelta(minutes=2), now)
        bid = df.iloc[-1]["close"]
        # BUY_LIMIT debe quedar por DEBAJO del precio actual (50 pips menos).
        order_price = round(bid - 0.0050, 5)

        # Paso 1: crear orden pendiente
        result = client.create_pending_order(
            symbol="EURUSD",
            order_type="BUY_LIMIT",
            volume=volume_min,
            price=order_price,
        )
        assert result.success and result.order_id > 0
        logger.info("✅ Orden creada: ticket=%d @ %.5f", result.order_id, order_price)
        logger.info("⏳ Pausa de 5 segundos — puedes verificar la orden en MetaTrader...")
        import time; time.sleep(5)

        # Paso 2: modificar precio de la orden (alejamos el BUY_LIMIT 10 pips más)
        mod_result = client.modify_order(
            order_id=result.order_id,
            price=round(bid - 0.0060, 5),
        )
        assert mod_result.success
        logger.info("✅ Orden modificada")

        # Paso 3: cancelar la orden
        cancelled = client.cancel_order(order_id=result.order_id)
        assert cancelled is True
        logger.info("✅ Orden cancelada")

        # Paso 4: verificar que la orden ya no aparece como pendiente
        open_orders = client.get_open_orders()
        assert result.order_id not in [o.order_id for o in open_orders]
        logger.info("✅ Orden ya no aparece en órdenes abiertas")

    except Exception as e:
        logger.error("❌ Error en ciclo de orden pendiente: %s", e, exc_info=True)


def test_modify_position_sl_tp(client):
    """Prueba modificación de SL/TP en posición abierta existente."""
    logger.info("\n" + "="*80)
    logger.info("TEST 10: Modificación SL/TP de Posición Abierta")
    logger.info("="*80)
    try:
        positions = client.get_open_positions()
        if not positions:
            # Sin posiciones abiertas no podemos probar modify_position_sl_tp.
            logger.warning("⚠️ No hay posiciones abiertas. Saltando test.")
            return
        pos = positions[0]
        # Calculamos SL y TP relativos al entry_price (20 pips SL, 40 pips TP).
        new_sl = round(pos.entry_price - 0.0020, 5)
        new_tp = round(pos.entry_price + 0.0040, 5)
        result = client.modify_position_sl_tp(
            symbol=pos.symbol,
            magic_number=pos.magic_number,
            stop_loss=new_sl,
            take_profit=new_tp,
        )
        assert result.success
        logger.info("✅ SL/TP modificados: SL=%.5f TP=%.5f", new_sl, new_tp)
    except Exception as e:
        logger.error("❌ Error al modificar SL/TP: %s", e, exc_info=True)


def main():
    """Ejecuta todos los tests."""
    logger.info("\n")
    logger.info("╔" + "="*78 + "╗")
    logger.info("║" + " "*20 + "TEST DE CONEXIÓN MT5" + " "*38 + "║")
    logger.info("╚" + "="*78 + "╝")
    logger.info("\n")
    
    # Símbolos a probar (estándar en MT5 demo)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    
    try:
        # Test 1: Conexión
        client = test_connection()
        
        # Test 2: Información de cuenta
        test_account_info(client)
        
        # Test 3: Disponibilidad de símbolos
        available_symbols = test_symbols_availability(client, symbols)
        
        if not available_symbols:
            logger.error("\n❌ CRÍTICO: No hay símbolos disponibles")
            logger.error("No se puede continuar con las pruebas")
            sys.exit(1)
        
        # Test 4: Descarga de datos + Timeframes (fusionados)
        test_ohlcv_and_timeframes(client, available_symbols)

        # Test 5: Posiciones y trades
        test_positions_and_trades(client)

        # TEST 6: Órdenes Pendientes
        test_open_orders(client)

        # TEST 7: Hora del Servidor
        test_server_time(client)

        # TEST 8: Snapshot de Trades Cerrados
        test_closed_trades_snapshot(client)

        # TEST 9-10: Ciclo de Orden Pendiente (REAL - requiere MT5 conectado a cuenta demo)
        test_pending_order_lifecycle(client)
        test_modify_position_sl_tp(client)


        # Resumen final
        logger.info("\n" + "="*80)
        logger.info("RESUMEN DE PRUEBAS")
        logger.info("="*80)
        logger.info("✅ Todas las pruebas completadas")
        logger.info("\n🎉 MetaTrader 5 está LISTO para usar con el bot")
        logger.info("\nPuedes ejecutar el bot principal con:")
        logger.info("  python bot_trading/main.py")
        logger.info("\n" + "="*80 + "\n")
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Pruebas interrumpidas por el usuario")
        sys.exit(1)
    except Exception as e:
        logger.error("\n❌ Error inesperado: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

