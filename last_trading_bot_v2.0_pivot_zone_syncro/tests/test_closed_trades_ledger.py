from __future__ import annotations

from datetime import datetime, timezone

from bot_trading.domain.entities import TradeRecord
from bot_trading.infrastructure.closed_trades_ledger import (
    ClosedTradesLedger,
    sort_trades_chronologically,
    trade_record_key,
)


def _trade(
    *,
    position_id: int | None = 777001,
    exit_deal_ticket: int | None = 4002,
    entry_hour: int = 1,
    exit_hour: int = 2,
    pnl: float = 10.0,
) -> TradeRecord:
    return TradeRecord(
        symbol="EURUSD",
        strategy_name="PivotZoneTest-M3",
        entry_time=datetime(2026, 3, 5, entry_hour, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 3, 5, exit_hour, 0, tzinfo=timezone.utc),
        entry_price=1.0800,
        exit_price=1.0810,
        size=0.10,
        pnl=pnl,
        stop_loss=None,
        take_profit=None,
        position_id=position_id,
        magic_number=99001,
        entry_deal_ticket=4001,
        exit_deal_ticket=exit_deal_ticket,
    )


def test_closed_trades_ledger_escribe_y_lee_trade_record(tmp_path) -> None:
    ledger = ClosedTradesLedger(tmp_path / "closed_trades_ledger.jsonl")
    trade = _trade()

    written = ledger.append_new([trade])
    loaded = ledger.load()

    assert written == [trade]
    assert len(loaded) == 1
    assert loaded[0].symbol == "EURUSD"
    assert loaded[0].entry_time == trade.entry_time
    assert loaded[0].exit_deal_ticket == 4002
    assert trade_record_key(loaded[0]) == "position_exit_deal:777001:4002"


def test_closed_trades_ledger_deduplica_por_position_y_exit_deal(tmp_path) -> None:
    ledger = ClosedTradesLedger(tmp_path / "closed_trades_ledger.jsonl")
    trade_a = _trade(pnl=10.0)
    trade_b = _trade(pnl=20.0)

    assert ledger.append_new([trade_a, trade_b]) == [trade_a]
    assert ledger.append_new([trade_a]) == []
    assert len(ledger.load()) == 1


def test_closed_trades_ledger_ignora_linea_corrupta(tmp_path, caplog) -> None:
    ledger_path = tmp_path / "closed_trades_ledger.jsonl"
    ledger = ClosedTradesLedger(ledger_path)
    ledger.append_new([_trade()])
    ledger_path.write_text(
        ledger_path.read_text(encoding="utf-8") + "{linea corrupta}\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        loaded = ledger.load()

    assert len(loaded) == 1
    assert "Linea corrupta ignorada" in caplog.text


def test_sort_trades_chronologically_ordena_por_entry_y_exit() -> None:
    late = _trade(position_id=2, exit_deal_ticket=20, entry_hour=4, exit_hour=5)
    early = _trade(position_id=1, exit_deal_ticket=10, entry_hour=1, exit_hour=2)

    assert sort_trades_chronologically([late, early]) == [early, late]
