"""Ledger persistente de trades cerrados.

El cursor de MT5 solo indica hasta que deal se leyo. Este ledger es la memoria
persistente de los cierres que el bot acepto y puede usar tras reinicios.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bot_trading.domain.entities import TradeRecord

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def ensure_utc_datetime(value: datetime) -> datetime:
    """Normaliza un datetime a UTC-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: object) -> datetime:
    if value is None:
        raise ValueError("datetime requerido")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return ensure_utc_datetime(parsed)


def _iso_utc(value: datetime) -> str:
    return ensure_utc_datetime(value).isoformat()


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _key_float(value: float) -> str:
    return f"{float(value):.12g}"


def trade_record_key(trade: TradeRecord) -> str:
    """Devuelve la identidad estable de un trade cerrado."""
    if trade.position_id is not None and trade.exit_deal_ticket is not None:
        return f"position_exit_deal:{int(trade.position_id)}:{int(trade.exit_deal_ticket)}"
    if trade.exit_deal_ticket is not None:
        return f"exit_deal:{int(trade.exit_deal_ticket)}"
    if trade.position_id is not None:
        return (
            "position_exit_time:"
            f"{int(trade.position_id)}:{_iso_utc(trade.exit_time)}"
        )
    return (
        "legacy:"
        f"{trade.symbol}:"
        f"{trade.strategy_name}:"
        f"{_iso_utc(trade.entry_time)}:"
        f"{_iso_utc(trade.exit_time)}:"
        f"{_key_float(trade.exit_price)}:"
        f"{_key_float(trade.size)}"
    )


def trade_sort_key(trade: TradeRecord) -> tuple[datetime, datetime, str]:
    """Clave cronologica estable para riesgo/drawdown."""
    return (
        ensure_utc_datetime(trade.entry_time),
        ensure_utc_datetime(trade.exit_time),
        trade_record_key(trade),
    )


def sort_trades_chronologically(trades: Iterable[TradeRecord]) -> list[TradeRecord]:
    return sorted(list(trades), key=trade_sort_key)


def dedupe_trades_chronologically(trades: Iterable[TradeRecord]) -> list[TradeRecord]:
    result: list[TradeRecord] = []
    seen: set[str] = set()
    for trade in sort_trades_chronologically(trades):
        key = trade_record_key(trade)
        if key in seen:
            continue
        seen.add(key)
        result.append(trade)
    return result


class ClosedTradesLedger:
    """Lee y escribe trades cerrados en JSONL con deduplicacion."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._known_trade_keys: set[str] = set()

    def load(self) -> list[TradeRecord]:
        """Carga trades validos del ledger, ignorando lineas corruptas."""
        self._known_trade_keys.clear()
        if not self.path.exists():
            return []

        trades: list[TradeRecord] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            logger.warning("No se pudo leer ledger de trades cerrados (%s): %s", self.path, exc)
            return []

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                trade = self._trade_from_payload(payload)
                key = trade_record_key(trade)
                if key in self._known_trade_keys:
                    continue
                self._known_trade_keys.add(key)
                trades.append(trade)
            except Exception as exc:
                logger.warning(
                    "Linea corrupta ignorada en ledger de trades cerrados %s:%d: %s",
                    self.path,
                    line_number,
                    exc,
                )

        return sort_trades_chronologically(trades)

    def append_new(self, trades: Iterable[TradeRecord]) -> list[TradeRecord]:
        """Anade solo trades no vistos y devuelve los que se escribieron."""
        existing = {trade_record_key(trade) for trade in self.load()}
        new_trades: list[TradeRecord] = []

        for trade in sort_trades_chronologically(trades):
            key = trade_record_key(trade)
            if key in existing:
                continue
            existing.add(key)
            new_trades.append(trade)

        if not new_trades:
            self._known_trade_keys = existing
            return []

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            for trade in new_trades:
                payload = self._payload_from_trade(trade)
                handle.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
                handle.write("\n")

        self._known_trade_keys = existing
        return new_trades

    @staticmethod
    def _payload_from_trade(trade: TradeRecord) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "trade_key": trade_record_key(trade),
            "symbol": trade.symbol,
            "strategy_name": trade.strategy_name,
            "entry_time": _iso_utc(trade.entry_time),
            "exit_time": _iso_utc(trade.exit_time),
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price),
            "size": float(trade.size),
            "pnl": float(trade.pnl),
            "stop_loss": _optional_float(trade.stop_loss),
            "take_profit": _optional_float(trade.take_profit),
            "position_id": _optional_int(trade.position_id),
            "magic_number": _optional_int(trade.magic_number),
            "entry_deal_ticket": _optional_int(trade.entry_deal_ticket),
            "exit_deal_ticket": _optional_int(trade.exit_deal_ticket),
            "written_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _trade_from_payload(payload: object) -> TradeRecord:
        if not isinstance(payload, dict):
            raise ValueError("payload JSON no es un objeto")

        return TradeRecord(
            symbol=str(payload["symbol"]),
            strategy_name=str(payload.get("strategy_name") or "Unknown"),
            entry_time=_parse_datetime(payload["entry_time"]),
            exit_time=_parse_datetime(payload["exit_time"]),
            entry_price=float(payload["entry_price"]),
            exit_price=float(payload["exit_price"]),
            size=float(payload["size"]),
            pnl=float(payload["pnl"]),
            stop_loss=_optional_float(payload.get("stop_loss")),
            take_profit=_optional_float(payload.get("take_profit")),
            position_id=_optional_int(payload.get("position_id")),
            magic_number=_optional_int(payload.get("magic_number")),
            entry_deal_ticket=_optional_int(payload.get("entry_deal_ticket")),
            exit_deal_ticket=_optional_int(payload.get("exit_deal_ticket")),
        )
