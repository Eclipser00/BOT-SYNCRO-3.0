"""Gestion de riesgo del bot de trading."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from bot_trading.domain.entities import AccountInfo, Position, RiskLimits, TradeRecord

logger = logging.getLogger(__name__)


@dataclass
class RiskManager:
    """Evalua limites de riesgo globales, por simbolo y por estrategia."""

    risk_limits: RiskLimits

    @staticmethod
    def _normalize_strategy_name(strategy_name: str) -> str:
        name = str(strategy_name or "").strip()
        if "-" not in name:
            return name
        base, suffix = name.rsplit("-", 1)
        if suffix.upper() in {
            "M1",
            "M3",
            "M5",
            "M9",
            "M15",
            "M30",
            "H1",
            "H4",
            "D1",
            "W1",
            "MN1",
        }:
            return base
        return name

    @staticmethod
    def _floating_pnl(open_positions: list[Position] | None) -> float:
        if not open_positions:
            return 0.0
        return sum(float(getattr(position, "profit", 0.0) or 0.0) for position in open_positions)

    def _calculate_drawdown(
        self,
        trades: list[TradeRecord],
        open_positions: list[Position] | None = None,
    ) -> float:
        """Calcula drawdown desde el maximo historico e incluye PnL flotante actual."""
        floating_pnl = self._floating_pnl(open_positions)
        if not trades and floating_pnl == 0.0:
            return 0.0

        initial_balance = self.risk_limits.initial_balance
        equity = initial_balance
        max_equity = initial_balance
        max_drawdown = 0.0

        for trade in sorted(trades, key=lambda t: (t.exit_time, t.entry_time, t.symbol, t.strategy_name)):
            equity += trade.pnl
            if equity > max_equity:
                max_equity = equity

            current_dd = ((max_equity - equity) / max_equity) * 100
            if current_dd > max_drawdown:
                max_drawdown = current_dd

        if floating_pnl != 0.0:
            equity_with_floating = equity + floating_pnl
            if equity_with_floating > max_equity:
                max_equity = equity_with_floating
            current_dd = ((max_equity - equity_with_floating) / max_equity) * 100
            if current_dd > max_drawdown:
                max_drawdown = current_dd
            equity = equity_with_floating

        logger.debug(
            "Drawdown calculado: %.2f%% (Equity: %.2f, Max: %.2f, FloatingPnL: %.2f)",
            max_drawdown,
            equity,
            max_equity,
            floating_pnl,
        )
        return max_drawdown

    def check_bot_risk_limits(
        self,
        trades: list[TradeRecord],
        open_positions: list[Position] | None = None,
    ) -> bool:
        """Valida si el bot puede operar segun el drawdown global."""
        if self.risk_limits.dd_global is None:
            return True
        drawdown = self._calculate_drawdown(trades, open_positions)
        allowed = drawdown <= self.risk_limits.dd_global
        if not allowed:
            logger.warning(
                "Limite de drawdown global superado: %.2f%% > %.2f%%",
                drawdown,
                self.risk_limits.dd_global,
            )
        return allowed

    def check_symbol_risk_limits(
        self,
        symbol: str,
        trades: list[TradeRecord],
        open_positions: list[Position] | None = None,
    ) -> bool:
        """Valida limites de riesgo por simbolo."""
        limit = self.risk_limits.dd_por_activo.get(symbol)
        if limit is None:
            return True
        filtered = [t for t in trades if t.symbol == symbol]
        filtered_positions = [p for p in (open_positions or []) if p.symbol == symbol]
        drawdown = self._calculate_drawdown(filtered, filtered_positions)
        allowed = drawdown <= limit
        if not allowed:
            logger.warning(
                "Limite de drawdown por simbolo %s superado: %.2f%% > %.2f%%",
                symbol,
                drawdown,
                limit,
            )
        return allowed

    def check_strategy_risk_limits(
        self,
        strategy_name: str,
        trades: list[TradeRecord],
        open_positions: list[Position] | None = None,
    ) -> bool:
        """Valida limites de riesgo por estrategia."""
        normalized_strategy = self._normalize_strategy_name(strategy_name)
        limit = self.risk_limits.dd_por_estrategia.get(strategy_name)
        if limit is None:
            for configured_name, configured_limit in self.risk_limits.dd_por_estrategia.items():
                if self._normalize_strategy_name(configured_name) == normalized_strategy:
                    limit = configured_limit
                    break
        if limit is None:
            return True
        filtered = [
            t for t in trades
            if self._normalize_strategy_name(t.strategy_name) == normalized_strategy
        ]
        filtered_positions = [
            p for p in (open_positions or [])
            if self._normalize_strategy_name(p.strategy_name) == normalized_strategy
        ]
        drawdown = self._calculate_drawdown(filtered, filtered_positions)
        allowed = drawdown <= limit
        if not allowed:
            logger.warning(
                "Limite de drawdown por estrategia %s superado: %.2f%% > %.2f%%",
                strategy_name,
                drawdown,
                limit,
            )
        return allowed

    def check_margin_limits(
        self,
        account_info: AccountInfo,
        required_margin: Optional[float] = None,
    ) -> bool:
        """Valida limites de margen antes de abrir nuevas posiciones."""
        max_margin_percent = self.risk_limits.max_margin_usage_percent
        if max_margin_percent is None:
            logger.debug("No hay limite de margen configurado, permitiendo orden")
            return True

        if account_info.equity <= 0:
            logger.warning("Equity es 0 o negativo, bloqueando orden por seguridad")
            return False

        margin_usage_percent = (account_info.margin / account_info.equity) * 100

        if margin_usage_percent > max_margin_percent:
            logger.warning(
                "Limite de margen superado: %.2f%% > %.2f%% (Margin: %.2f, Equity: %.2f)",
                margin_usage_percent,
                max_margin_percent,
                account_info.margin,
                account_info.equity,
            )
            return False

        if required_margin is not None and required_margin > 0:
            if account_info.margin_free < required_margin:
                logger.warning(
                    "Margen libre insuficiente: %.2f < %.2f requerido (MarginFree: %.2f)",
                    account_info.margin_free,
                    required_margin,
                    account_info.margin_free,
                )
                return False

            total_margin = account_info.margin + required_margin
            total_margin_percent = (total_margin / account_info.equity) * 100

            if total_margin_percent > max_margin_percent:
                logger.warning(
                    "Abrir esta posicion superaria el limite de margen: %.2f%% > %.2f%% "
                    "(Margin actual: %.2f, Requerido: %.2f, Total: %.2f)",
                    total_margin_percent,
                    max_margin_percent,
                    account_info.margin,
                    required_margin,
                    total_margin,
                )
                return False

        logger.debug(
            "Validacion de margen exitosa: %.2f%% usado (limite: %.2f%%), "
            "MarginFree: %.2f",
            margin_usage_percent,
            max_margin_percent,
            account_info.margin_free,
        )
        return True
