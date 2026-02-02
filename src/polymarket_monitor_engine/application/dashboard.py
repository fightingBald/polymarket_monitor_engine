from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.models import BookSnapshot, Market, TradeTick


@dataclass(slots=True)
class TradeWindow:
    entries: deque[tuple[int, float]] = field(default_factory=deque)
    total: float = 0.0

    def add(self, ts_ms: int, notional: float) -> None:
        self.entries.append((ts_ms, notional))
        self.total += notional

    def trim(self, cutoff_ms: int) -> None:
        while self.entries and self.entries[0][0] < cutoff_ms:
            _, notional = self.entries.popleft()
            self.total -= notional


@dataclass(slots=True)
class MarketRow:
    token_id: str
    market_id: str
    title: str
    category: str
    side: str | None
    last_trade_price: float | None = None
    last_trade_size: float | None = None
    last_trade_notional: float | None = None
    last_trade_ts: int | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    mid: float | None = None
    last_book_ts: int | None = None
    window: TradeWindow = field(default_factory=TradeWindow)


@dataclass(slots=True)
class GhostRow:
    market_id: str
    title: str
    category: str
    reason: str


@dataclass(slots=True)
class DashboardRowSnapshot:
    token_id: str
    market_id: str
    title: str
    category: str
    side: str | None
    subscribable: bool
    note: str | None
    outcome_summary: str | None
    last_price: float | None
    best_bid: float | None
    best_ask: float | None
    vol_1m: float
    last_trade_notional: float | None
    last_trade_age_s: float | None
    last_book_age_s: float | None


@dataclass(slots=True)
class DashboardSnapshot:
    rows: list[DashboardRowSnapshot]
    token_count: int
    market_count: int
    last_refresh_duration_ms: int | None
    last_refresh_age_s: float | None
    uptime_s: float


class TerminalDashboard:
    def __init__(self, refresh_hz: float, max_rows: int) -> None:
        self._refresh_hz = max(0.5, refresh_hz)
        self._max_rows = max(5, max_rows)
        self._rows: dict[str, MarketRow] = {}
        self._ghost_rows: dict[str, GhostRow] = {}
        self._lock = asyncio.Lock()
        self._last_refresh_ts_ms: int | None = None
        self._last_refresh_duration_ms: int | None = None
        self._start_ts = time.time()
        self._stop_event = asyncio.Event()
        self._console = Console()

    async def update_registry(self, token_meta: dict[str, TokenMeta]) -> None:
        async with self._lock:
            new_rows: dict[str, MarketRow] = {}
            for token_id, meta in token_meta.items():
                row = self._rows.get(token_id)
                if row is None:
                    row = MarketRow(
                        token_id=token_id,
                        market_id=meta.market_id,
                        title=meta.title or "(unknown)",
                        category=meta.category,
                        side=meta.side,
                    )
                else:
                    row.market_id = meta.market_id
                    row.title = meta.title or row.title
                    row.category = meta.category
                    row.side = meta.side
                new_rows[token_id] = row
            self._rows = new_rows

    async def update_trade(self, trade: TradeTick) -> None:
        async with self._lock:
            row = self._rows.get(trade.token_id)
            if row is None:
                return
            notional = trade.price * trade.size
            row.last_trade_price = trade.price
            row.last_trade_size = trade.size
            row.last_trade_notional = notional
            row.last_trade_ts = trade.ts_ms
            row.window.add(trade.ts_ms, notional)
            row.window.trim(trade.ts_ms - 60_000)

    async def update_book(self, book: BookSnapshot) -> None:
        async with self._lock:
            row = self._rows.get(book.token_id)
            if row is None:
                return
            best_bid = max((level.price for level in book.bids), default=None)
            best_ask = min((level.price for level in book.asks), default=None)
            row.best_bid = best_bid
            row.best_ask = best_ask
            if best_bid is not None and best_ask is not None:
                row.mid = (best_bid + best_ask) / 2.0
            row.last_book_ts = book.ts_ms

    async def record_refresh(self, duration_ms: int) -> None:
        async with self._lock:
            self._last_refresh_duration_ms = duration_ms
            self._last_refresh_ts_ms = int(time.time() * 1000)

    async def update_unsubscribable(self, markets: list[Market], reason: str) -> None:
        async with self._lock:
            new_ghosts: dict[str, GhostRow] = {}
            for market in markets:
                if not market.market_id:
                    continue
                new_ghosts[market.market_id] = GhostRow(
                    market_id=market.market_id,
                    title=market.question or "(unknown)",
                    category=market.category or "top",
                    reason=reason,
                )
            self._ghost_rows = new_ghosts

    async def snapshot(self, now_ms: int | None = None) -> DashboardSnapshot:
        async with self._lock:
            now_ms = now_ms or int(time.time() * 1000)
            rows: list[DashboardRowSnapshot] = []
            market_ids = set()
            grouped: dict[str, list[MarketRow]] = {}
            for row in self._rows.values():
                grouped.setdefault(row.market_id, []).append(row)

            for market_id, group in grouped.items():
                for row in group:
                    row.window.trim(now_ms - 60_000)
                if _is_multi_outcome(group):
                    rows.append(_build_multi_row(group, now_ms))
                    market_ids.add(market_id)
                else:
                    for row in group:
                        last_trade_age = (
                            (now_ms - row.last_trade_ts) / 1000 if row.last_trade_ts else None
                        )
                        last_book_age = (
                            (now_ms - row.last_book_ts) / 1000 if row.last_book_ts else None
                        )
                        rows.append(
                            DashboardRowSnapshot(
                                token_id=row.token_id,
                                market_id=row.market_id,
                                title=row.title,
                                category=row.category,
                                side=row.side,
                                subscribable=True,
                                note=None,
                                outcome_summary=None,
                                last_price=row.last_trade_price or row.mid,
                                best_bid=row.best_bid,
                                best_ask=row.best_ask,
                                vol_1m=row.window.total,
                                last_trade_notional=row.last_trade_notional,
                                last_trade_age_s=last_trade_age,
                                last_book_age_s=last_book_age,
                            )
                        )
                        market_ids.add(row.market_id)

            for ghost in self._ghost_rows.values():
                rows.append(
                    DashboardRowSnapshot(
                        token_id="",
                        market_id=ghost.market_id,
                        title=ghost.title,
                        category=ghost.category,
                        side=None,
                        subscribable=False,
                        note=ghost.reason,
                        outcome_summary=None,
                        last_price=None,
                        best_bid=None,
                        best_ask=None,
                        vol_1m=0.0,
                        last_trade_notional=None,
                        last_trade_age_s=None,
                        last_book_age_s=None,
                    )
                )
                market_ids.add(ghost.market_id)

            rows.sort(key=lambda item: (item.category, item.title))
            rows = rows[: self._max_rows]

            last_refresh_age = (
                (now_ms - self._last_refresh_ts_ms) / 1000
                if self._last_refresh_ts_ms
                else None
            )
            return DashboardSnapshot(
                rows=rows,
                token_count=len(self._rows),
                market_count=len(market_ids),
                last_refresh_duration_ms=self._last_refresh_duration_ms,
                last_refresh_age_s=last_refresh_age,
                uptime_s=time.time() - self._start_ts,
            )

    async def run(self) -> None:
        refresh_sec = 1 / self._refresh_hz
        try:
            with Live(
                self._render(await self.snapshot()),
                console=self._console,
                refresh_per_second=self._refresh_hz,
                transient=False,
            ) as live:
                while not self._stop_event.is_set():
                    live.update(self._render(await self.snapshot()))
                    await asyncio.sleep(refresh_sec)
        except asyncio.CancelledError:
            self._stop_event.set()
            raise

    async def stop(self) -> None:
        self._stop_event.set()

    @staticmethod
    def _render(snapshot: DashboardSnapshot) -> Table:
        title = (
            f"🚦 Polymarket Live | tokens {snapshot.token_count} | markets {snapshot.market_count}"
        )
        caption = _build_caption(snapshot)
        table = Table(title=title, caption=caption, show_lines=False)
        table.add_column("分类", style="cyan", no_wrap=True)
        table.add_column("市场", style="white", overflow="ellipsis", ratio=3)
        table.add_column("状态", no_wrap=True)
        table.add_column("方向", no_wrap=True)
        table.add_column("最新", no_wrap=True)
        table.add_column("盘口(B/A)", no_wrap=True)
        table.add_column("1m 成交", no_wrap=True)
        table.add_column("最近成交", no_wrap=True)
        table.add_column("更新", no_wrap=True)

        if not snapshot.rows:
            table.add_row("-", "暂无数据", "-", "-", "-", "-", "-", "-")
            return table

        for row in snapshot.rows:
            if row.outcome_summary:
                side_text = Text(row.outcome_summary, style="bold white")
            elif row.subscribable:
                side_text = _fmt_side(row.side)
            else:
                side_text = Text("—", style="bright_black")
            last_price = _fmt_price(row.last_price)
            bid_ask = f"{_fmt_price(row.best_bid)} / {_fmt_price(row.best_ask)}"
            vol_1m = _fmt_money(row.vol_1m)
            last_trade = _fmt_money(row.last_trade_notional)
            update = _fmt_update(row.last_trade_age_s, row.last_book_age_s)
            status = "✅" if row.subscribable else "🚫 无 orderbook"
            if row.note:
                status = f"{status} {row.note}"
            style = None if row.subscribable else "bright_black"
            table.add_row(
                row.category,
                row.title,
                status,
                side_text,
                last_price,
                bid_ask,
                vol_1m,
                last_trade,
                update,
                style=style,
            )

        return table


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}¢"


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _fmt_side(value: str | None) -> Text:
    if value is None:
        return Text("?", style="bold yellow")
    upper = value.upper()
    if upper == "YES":
        return Text("YES", style="bold green")
    if upper == "NO":
        return Text("NO", style="bold red")
    return Text(upper, style="bold yellow")


def _fmt_update(trade_age: float | None, book_age: float | None) -> str:
    trade = f"T:{trade_age:.0f}s" if trade_age is not None else "T:—"
    book = f"B:{book_age:.0f}s" if book_age is not None else "B:—"
    return f"{trade} {book}"


def _build_caption(snapshot: DashboardSnapshot) -> str:
    refresh = (
        f"刷新耗时 {snapshot.last_refresh_duration_ms}ms"
        if snapshot.last_refresh_duration_ms is not None
        else "刷新耗时 n/a"
    )
    refresh_age = (
        f"| 刷新距今 {snapshot.last_refresh_age_s:.0f}s"
        if snapshot.last_refresh_age_s is not None
        else ""
    )
    uptime = f"| 运行 {snapshot.uptime_s/60:.1f}m"
    return f"{refresh} {refresh_age} {uptime}".strip()


def _is_multi_outcome(rows: list[MarketRow]) -> bool:
    if len(rows) > 2:
        return True
    if len(rows) <= 1:
        return False
    sides = {((row.side or "").upper()) for row in rows}
    return not sides.issubset({"YES", "NO"})


def _build_multi_row(rows: list[MarketRow], now_ms: int) -> DashboardRowSnapshot:
    title = rows[0].title
    category = rows[0].category
    market_id = rows[0].market_id

    def price_value(row: MarketRow) -> float | None:
        return row.last_trade_price if row.last_trade_price is not None else row.mid

    def sort_key(row: MarketRow) -> float:
        value = price_value(row)
        return value if value is not None else -1.0

    sorted_rows = sorted(rows, key=sort_key, reverse=True)
    top_row = sorted_rows[0]
    outcome_summary = _build_outcome_summary(sorted_rows, limit=4)

    trade_ages = [
        (now_ms - row.last_trade_ts) / 1000
        for row in rows
        if row.last_trade_ts is not None
    ]
    book_ages = [
        (now_ms - row.last_book_ts) / 1000
        for row in rows
        if row.last_book_ts is not None
    ]

    return DashboardRowSnapshot(
        token_id="",
        market_id=market_id,
        title=title,
        category=category,
        side=None,
        subscribable=True,
        note="多选盘",
        outcome_summary=outcome_summary,
        last_price=price_value(top_row),
        best_bid=top_row.best_bid,
        best_ask=top_row.best_ask,
        vol_1m=sum(row.window.total for row in rows),
        last_trade_notional=max(
            (row.last_trade_notional for row in rows if row.last_trade_notional is not None),
            default=None,
        ),
        last_trade_age_s=min(trade_ages) if trade_ages else None,
        last_book_age_s=min(book_ages) if book_ages else None,
    )


def _build_outcome_summary(rows: list[MarketRow], limit: int) -> str:
    lines: list[str] = []
    for row in rows[:limit]:
        name = row.side or "?"
        lines.append(f"{name} {_fmt_price(row.last_trade_price or row.mid)}")
    if len(rows) > limit:
        lines.append(f"... 还有 {len(rows) - limit} 个")
    return "\n".join(lines)
