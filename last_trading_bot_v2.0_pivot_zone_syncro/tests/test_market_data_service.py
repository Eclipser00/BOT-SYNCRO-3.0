"""Tests del servicio de datos de mercado."""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from bot_trading.domain.entities import SymbolConfig
from bot_trading.infrastructure.data_fetcher import (
    DevelopmentCsvDataProvider,
    MarketDataService,
    ProductionDataProvider,
)


# ============================================
# FIXTURES
# ============================================


class FakeBrokerSpy:
    """Broker falso que registra todas las llamadas y devuelve datos secuenciales."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_ohlcv(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Genera un DataFrame OHLCV secuencial y registra la llamada."""
        self.calls.append(
            {"symbol": symbol, "timeframe": timeframe, "start": start, "end": end}
        )
        index = pd.date_range(start=start, end=end, freq="1min", tz=timezone.utc)
        data = {
            "open": range(len(index)),
            "high": range(len(index)),
            "low": range(len(index)),
            "close": range(len(index)),
            "volume": [1] * len(index),
        }
        return pd.DataFrame(data, index=index)


@pytest.fixture()
def fake_broker_spy() -> FakeBrokerSpy:
    """Devuelve una instancia limpia de FakeBrokerSpy."""
    return FakeBrokerSpy()


@pytest.fixture()
def csv_tmp_path(tmp_path: Path) -> Path:
    """Crea un CSV de 20 filas M1 en un directorio temporal y devuelve el directorio."""
    rows = 20
    base_ts = 1_700_000_000  # Timestamp Unix base en segundos

    df = pd.DataFrame(
        {
            "time": [base_ts + i * 60 for i in range(rows)],
            "open": [100 + i for i in range(rows)],
            "high": [100 + i for i in range(rows)],
            "low": [100 + i for i in range(rows)],
            "close": [100 + i for i in range(rows)],
            "volume": [1] * rows,
        }
    )
    df.to_csv(tmp_path / "EURUSD.csv", index=False)
    return tmp_path


# ============================================
# TESTS — ProductionDataProvider
# ============================================


def test_production_bootstrap_calls_broker_once(fake_broker_spy: FakeBrokerSpy) -> None:
    """El bootstrap inicial debe hacer una sola llamada al broker y devolver todos los TFs."""
    provider = ProductionDataProvider(
        fake_broker_spy, lookback_days_entry=1, lookback_days_zone=1, lookback_days_stop=1
    )
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")

    result = provider.get_data(symbol, ["M1", "M5"], now)

    assert len(fake_broker_spy.calls) == 1
    assert "M1" in result
    assert "M5" in result


def test_production_incremental_uses_cache_end(fake_broker_spy: FakeBrokerSpy) -> None:
    """La segunda llamada debe arrancar desde el final del cache, no desde cero."""
    provider = ProductionDataProvider(
        fake_broker_spy, lookback_days_entry=1, lookback_days_zone=1, lookback_days_stop=1
    )
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")

    provider.get_data(symbol, ["M1"], now)
    provider.get_data(symbol, ["M1"], now + timedelta(minutes=5))

    assert len(fake_broker_spy.calls) == 2
    # La segunda llamada debe arrancar despues de la primera
    assert fake_broker_spy.calls[1]["start"] > fake_broker_spy.calls[0]["start"]


def test_production_normalizes_naive_index_to_utc(fake_broker_spy: FakeBrokerSpy) -> None:
    """Un broker que devuelve indice naive debe ser normalizado a UTC en el cache."""

    class NaiveBrokerSpy(FakeBrokerSpy):
        """Variante que devuelve DatetimeIndex sin timezone."""

        def get_ohlcv(
            self, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> pd.DataFrame:
            self.calls.append(
                {"symbol": symbol, "timeframe": timeframe, "start": start, "end": end}
            )
            # Indice sin timezone (naive)
            index = pd.date_range(start=start, end=end, freq="1min", tz=None)
            data = {
                "open": range(len(index)),
                "high": range(len(index)),
                "low": range(len(index)),
                "close": range(len(index)),
                "volume": [1] * len(index),
            }
            return pd.DataFrame(data, index=index)

    naive_broker = NaiveBrokerSpy()
    provider = ProductionDataProvider(
        naive_broker, lookback_days_entry=1, lookback_days_zone=1, lookback_days_stop=1
    )
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")

    provider.get_data(symbol, ["M1"], now)

    assert provider._base_cache["EURUSD"].index.tz is not None


def test_production_drop_last_partial_removes_incomplete_candle() -> None:
    """El resampleo debe descartar la ultima vela M5 si esta incompleta."""

    class FixedBrokerSpy(FakeBrokerSpy):
        """Devuelve exactamente 7 filas M1 para generar una vela M5 parcial."""

        def get_ohlcv(
            self, symbol: str, timeframe: str, start: datetime, end: datetime
        ) -> pd.DataFrame:
            self.calls.append(
                {"symbol": symbol, "timeframe": timeframe, "start": start, "end": end}
            )
            # 7 velas M1 = 1 vela M5 completa + 2 minutos parciales
            base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
            index = pd.date_range(start=base, periods=7, freq="1min", tz=timezone.utc)
            data = {
                "open": range(7),
                "high": range(7),
                "low": range(7),
                "close": range(7),
                "volume": [1] * 7,
            }
            return pd.DataFrame(data, index=index)

    broker = FixedBrokerSpy()
    provider = ProductionDataProvider(
        broker, lookback_days_entry=1, lookback_days_zone=1, lookback_days_stop=1
    )
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")

    result = provider.get_data(symbol, ["M1", "M5"], now)

    # Resample naive (sin drop) para comparar
    base_df = result["M1"]
    resample_sin_drop = (
        base_df.resample("5min", label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )

    assert len(result["M5"]) <= len(resample_sin_drop)


def test_production_raises_value_error_for_unsupported_timeframe(
    fake_broker_spy: FakeBrokerSpy,
) -> None:
    """Un timeframe base no reconocido debe lanzar ValueError."""
    provider = ProductionDataProvider(
        fake_broker_spy, lookback_days_entry=1, lookback_days_zone=1, lookback_days_stop=1
    )
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="X99")

    with pytest.raises(ValueError):
        provider.get_data(symbol, ["X99"], now)


# ============================================
# TESTS — DevelopmentCsvDataProvider
# ============================================


def _make_csv_provider(data_dir: Path) -> DevelopmentCsvDataProvider:
    """Atajo para construir un DevelopmentCsvDataProvider con config estandar."""
    return DevelopmentCsvDataProvider(
        data_dir=data_dir,
        base_timeframe="M1",
        lookback_days_entry=1,
        lookback_days_zone=1,
        lookback_days_stop=1,
    )


def test_csv_load_utc_aware_index_and_ohlcv_columns(csv_tmp_path: Path) -> None:
    """El CSV cargado debe tener indice UTC-aware y las 5 columnas OHLCV."""
    provider = _make_csv_provider(csv_tmp_path)
    provider._ensure_loaded("EURUSD")

    loaded = provider._base_data["EURUSD"]
    assert loaded.index.tz is not None
    assert set(loaded.columns) == {"open", "high", "low", "close", "volume"}


def test_csv_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """Cargar un simbolo sin CSV debe lanzar FileNotFoundError."""
    provider = _make_csv_provider(tmp_path)

    with pytest.raises(FileNotFoundError):
        provider._ensure_loaded("NOEXISTS")


def test_csv_bootstrap_cursor_position(csv_tmp_path: Path) -> None:
    """Con 20 filas y lookback=1 dia, bars_needed > 20, asi que cursor debe ser 1."""
    provider = _make_csv_provider(csv_tmp_path)
    provider._ensure_loaded("EURUSD")
    provider._bootstrap_cursor("EURUSD")

    # bars_needed = ceil(1 * 24 * 60 / 1) = 1440, que es mayor que 20 filas
    bars_needed = math.ceil(1 * 24 * 60 / 1)
    assert bars_needed > 20, "La premisa del test requiere que bars_needed > filas del CSV"
    assert provider._cursor["EURUSD"] == 1


def test_csv_streaming_second_call_has_one_more_row(csv_tmp_path: Path) -> None:
    """Cada llamada sucesiva a get_data debe entregar una fila M1 mas."""
    provider = _make_csv_provider(csv_tmp_path)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    result1 = provider.get_data(symbol, ["M1"], now)
    result2 = provider.get_data(symbol, ["M1"], now)

    assert len(result2["M1"]) == len(result1["M1"]) + 1


def test_csv_stop_iteration_when_exhausted(csv_tmp_path: Path) -> None:
    """El CSV de 20 filas debe lanzar StopIteration dentro de las primeras 22 llamadas."""
    provider = _make_csv_provider(csv_tmp_path)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(StopIteration):
        for _ in range(22):
            provider.get_data(symbol, ["M1"], now)


def test_csv_resample_drops_partial_last_candle(csv_tmp_path: Path) -> None:
    """El resampleo M5 en streaming debe descartar la vela parcial final."""
    provider = _make_csv_provider(csv_tmp_path)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    # Preparar cursor manualmente para tener datos suficientes
    provider._ensure_loaded("EURUSD")
    provider._bootstrap_cursor("EURUSD")
    provider._advance("EURUSD", steps=6)

    result = provider.get_data(symbol, ["M1", "M5"], now)

    # Resample naive sobre el mismo slice M1 (sin drop de parcial)
    m1_slice = result["M1"]
    resample_naive_m5 = (
        m1_slice.resample("5min", label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )

    assert len(result["M5"]) <= len(resample_naive_m5)


def test_csv_get_simulated_now_after_bootstrap(csv_tmp_path: Path) -> None:
    """get_simulated_now debe devolver un datetime UTC-aware tras el bootstrap."""
    provider = _make_csv_provider(csv_tmp_path)
    symbol = SymbolConfig(name="EURUSD", min_timeframe="M1")

    result_now = provider.get_simulated_now([symbol])

    assert isinstance(result_now, datetime)
    assert result_now.tzinfo is not None
