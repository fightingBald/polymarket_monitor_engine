from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import httpx
import structlog

from polymarket_monitor_engine.domain.models import Market, OutcomeToken, Tag

logger = structlog.get_logger(__name__)


class GammaHttpCatalog:
    def __init__(self, base_url: str, timeout_sec: float, page_size: int) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_sec)
        self._page_size = page_size

    async def list_tags(self) -> list[Tag]:
        items = await self._paginate("/tags", {})
        parsed: list[Tag] = []
        for raw in items:
            tag_id = str(raw.get("id") or raw.get("tag_id") or "")
            if not tag_id:
                continue
            parsed.append(
                Tag(
                    tag_id=tag_id,
                    slug=raw.get("slug"),
                    name=raw.get("name"),
                    raw=raw or None,
                )
            )
        return parsed

    async def list_markets(self, tag_id: str, active: bool = True, closed: bool = False) -> list[Market]:
        params = {
            "tag_id": tag_id,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": self._page_size,
        }
        items = await self._paginate("/markets", params)
        return [self._parse_market(item) for item in items]

    async def close(self) -> None:
        await self._client.aclose()

    async def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        page = 1
        next_cursor: str | None = None

        while True:
            query = dict(params)
            query.setdefault("limit", self._page_size)
            if next_cursor:
                query["cursor"] = next_cursor
            else:
                query["page"] = page

            resp = await self._client.get(path, params=query)
            resp.raise_for_status()
            payload = resp.json()
            items, next_cursor = self._extract_items(payload)
            collected.extend(items)

            if next_cursor:
                continue

            if not items or len(items) < self._page_size:
                break
            page += 1

        logger.info("gamma_paginate", path=path, count=len(collected))
        return collected

    @staticmethod
    def _extract_items(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
        next_cursor: str | None = None
        items: Iterable[Any]

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("data") or payload.get("results") or []
            next_cursor = payload.get("next") or payload.get("cursor")
        else:
            items = []

        parsed = [item for item in items if isinstance(item, dict)]
        return parsed, next_cursor

    @staticmethod
    def _parse_market(raw: dict[str, Any]) -> Market:
        market_id = str(raw.get("id") or raw.get("market_id") or raw.get("marketId"))
        question = raw.get("question") or raw.get("title") or ""
        active = bool(raw.get("active", True))
        closed = bool(raw.get("closed", False))
        resolved = bool(raw.get("resolved", False))
        end_ts = GammaHttpCatalog._parse_end_ts(raw.get("end_ts") or raw.get("endDate"))
        liquidity = GammaHttpCatalog._to_float(raw.get("liquidity") or raw.get("liquidityUSD"))
        volume_24h = GammaHttpCatalog._to_float(raw.get("volume_24h") or raw.get("volume24h"))

        outcomes = GammaHttpCatalog._extract_outcomes(raw)
        token_ids = [outcome.token_id for outcome in outcomes if outcome.token_id]

        return Market(
            market_id=market_id,
            question=question,
            active=active,
            closed=closed,
            resolved=resolved,
            end_ts=end_ts,
            liquidity=liquidity,
            volume_24h=volume_24h,
            token_ids=token_ids,
            outcomes=outcomes,
            raw=raw,
        )

    @staticmethod
    def _parse_end_ts(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return int(dt.astimezone(timezone.utc).timestamp() * 1000)
                except ValueError:
                    return None
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_outcomes(raw: dict[str, Any]) -> list[OutcomeToken]:
        outcomes: list[OutcomeToken] = []

        def add_token(token_raw: dict[str, Any]) -> None:
            token_id = GammaHttpCatalog._coerce_token_id(token_raw)
            side = token_raw.get("side") or token_raw.get("name") or token_raw.get("title")
            if token_id:
                outcomes.append(OutcomeToken(token_id=token_id, side=side, raw=token_raw))

        if isinstance(raw.get("outcomes"), list):
            for outcome in raw["outcomes"]:
                if isinstance(outcome, dict):
                    add_token(outcome)
                elif isinstance(outcome, str):
                    outcomes.append(OutcomeToken(token_id="", side=outcome))

        if isinstance(raw.get("tokens"), list):
            for token in raw["tokens"]:
                if isinstance(token, dict):
                    add_token(token)

        return outcomes

    @staticmethod
    def _coerce_token_id(token_raw: dict[str, Any]) -> str | None:
        for key in ("token_id", "tokenId", "clobTokenId", "asset_id", "assetId", "id"):
            if key in token_raw and token_raw[key] is not None:
                return str(token_raw[key])
        return None
