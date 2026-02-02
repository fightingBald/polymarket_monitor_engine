from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from aiolimiter import AsyncLimiter
from cachetools import TTLCache
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from polymarket_monitor_engine.domain.models import Market, OutcomeToken, Tag

logger = structlog.get_logger(__name__)


class GammaHttpCatalog:
    def __init__(
        self,
        base_url: str,
        timeout_sec: float,
        page_size: int,
        use_events_endpoint: bool,
        related_tags: bool,
        request_interval_ms: int,
        tags_cache_sec: int,
        retry_max_attempts: int,
        events_limit_per_category: int | None = None,
        events_sort_primary: str | None = "volume24hr",
        events_sort_secondary: str | None = "liquidity",
        events_sort_desc: bool = True,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_sec)
        self._page_size = page_size
        self._use_events_endpoint = use_events_endpoint
        self._related_tags = related_tags
        self._request_interval_ms = request_interval_ms
        self._tags_cache_sec = tags_cache_sec
        self._retry_max_attempts = retry_max_attempts
        self._events_limit_per_category = self._normalize_limit(events_limit_per_category)
        self._events_sort_primary = self._normalize_sort_key(events_sort_primary)
        self._events_sort_secondary = self._normalize_sort_key(events_sort_secondary)
        self._events_sort_desc = bool(events_sort_desc)
        self._tags_cache: TTLCache[str, list[Tag]] = TTLCache(
            maxsize=1,
            ttl=max(1, int(tags_cache_sec)),
        )
        self._rate_limiter: AsyncLimiter | None = None
        if self._request_interval_ms > 0:
            period = max(0.001, self._request_interval_ms / 1000.0)
            self._rate_limiter = AsyncLimiter(1, period)

    async def list_tags(self) -> list[Tag]:
        cached = self._tags_cache.get("tags")
        if cached is not None:
            return cached

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
        self._tags_cache["tags"] = parsed
        return parsed

    async def list_markets(
        self,
        tag_id: str,
        active: bool = True,
        closed: bool = False,
    ) -> list[Market]:
        if self._use_events_endpoint:
            params = {
                "tag_id": tag_id,
                "closed": str(closed).lower(),
                "limit": self._page_size,
            }
            if self._related_tags:
                params["related_tags"] = "true"
            if self._events_sort_primary:
                params["order"] = self._events_sort_primary
                params["ascending"] = str(not self._events_sort_desc).lower()
            events = await self._paginate(
                "/events",
                params,
            )
            events = [event for event in events if self._event_is_active(event)]
            events = self._sort_events(events)
            if (
                self._events_limit_per_category is not None
                and len(events) > self._events_limit_per_category
            ):
                events = events[: self._events_limit_per_category]
            markets: list[Market] = []
            for event in events:
                markets.extend(self._extract_markets_from_event(event))
            return [
                m
                for m in markets
                if m.market_id
                and (m.active if active else True)
                and (not m.closed if not closed else True)
                and not m.resolved
            ]

        params = {
            "tag_id": tag_id,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": self._page_size,
        }
        items = await self._paginate("/markets", params)
        markets = [self._parse_market(item) for item in items]
        return [m for m in markets if m.market_id]

    async def list_top_markets(
        self,
        limit: int,
        order: str | None,
        ascending: bool,
        featured_only: bool,
        closed: bool = False,
    ) -> list[Market]:
        params: dict[str, Any] = {
            "closed": str(closed).lower(),
            "limit": max(1, int(limit)),
            "offset": 0,
        }
        if featured_only:
            params["featured"] = "true"
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()

        payload = await self._request_json("/events", params)
        events = self._extract_items(payload)
        if limit and len(events) > limit:
            events = events[:limit]

        markets: list[Market] = []
        for event in events:
            markets.extend(self._extract_markets_from_event(event))

        return [m for m in markets if m.market_id and m.active and not m.closed and not m.resolved]

    async def close(self) -> None:
        await self._client.aclose()

    async def _paginate(
        self,
        path: str,
        params: dict[str, Any],
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        offset = 0
        limit = int(params.get("limit", self._page_size))
        max_items = self._normalize_limit(max_items)

        while True:
            query = dict(params)
            page_limit = limit
            if max_items is not None:
                remaining = max_items - len(collected)
                if remaining <= 0:
                    break
                page_limit = min(page_limit, remaining)
            if page_limit <= 0:
                break
            query["limit"] = page_limit
            query["offset"] = offset

            payload = await self._request_json(path, query)
            items = self._extract_items(payload)
            collected.extend(items)

            if not items or len(items) < page_limit:
                break
            offset += page_limit

        if max_items is not None and len(collected) > max_items:
            collected = collected[:max_items]

        log_payload = {"path": path, "count": len(collected)}
        if max_items is not None:
            log_payload["limit"] = max_items
        logger.info("gamma_paginate", **log_payload)
        return collected

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        items: Iterable[Any]

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("data") or payload.get("results") or []
        else:
            items = []

        return [item for item in items if isinstance(item, dict)]

    async def _rate_limit_pause(self) -> None:
        if self._rate_limiter is None:
            return
        async with self._rate_limiter:
            return None

    async def _request_json(self, path: str, params: dict[str, Any]) -> Any:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._retry_max_attempts),
            wait=wait_exponential_jitter(initial=0.5, max=5),
            retry=retry_if_exception(self._is_retryable_http_error),
            reraise=True,
        ):
            with attempt:
                await self._rate_limit_pause()
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        "Retryable HTTP status",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp.json()

        return None

    @staticmethod
    def _is_retryable_http_error(exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return status == 429 or 500 <= status < 600
        return isinstance(exc, httpx.RequestError)

    @staticmethod
    def _normalize_limit(value: int | None) -> int | None:
        if value is None:
            return None
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return None
        if limit <= 0:
            return None
        return limit

    @staticmethod
    def _normalize_sort_key(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _sort_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._events_sort_primary:
            return events
        primary = self._events_sort_primary
        secondary = self._events_sort_secondary
        reverse = self._events_sort_desc

        def sort_key(event: dict[str, Any]) -> tuple[float, float]:
            primary_value = self._event_metric(event, primary)
            secondary_value = self._event_metric(event, secondary)
            return (primary_value, secondary_value)

        sorted_events = sorted(events, key=sort_key, reverse=reverse)
        logger.info(
            "gamma_events_sort",
            primary=primary,
            secondary=secondary,
            desc=reverse,
            count=len(sorted_events),
        )
        return sorted_events

    @staticmethod
    def _event_metric(event: dict[str, Any], key: str | None) -> float:
        if not key:
            return 0.0
        key_norm = key.strip().lower()
        if key_norm in {"volume24hr", "volume24h", "volume_24h", "volume24hrclob"}:
            return GammaHttpCatalog._event_volume_24h(event)
        if key_norm in {"liquidity", "liquidityusd", "liquiditynum"}:
            return GammaHttpCatalog._event_liquidity(event)
        return 0.0

    @staticmethod
    def _event_volume_24h(event: dict[str, Any]) -> float:
        for key in ("volume_24h", "volume24h", "volume24hr", "volume24hrClob"):
            value = GammaHttpCatalog._to_float(event.get(key))
            if value is not None:
                return value
        return GammaHttpCatalog._sum_market_metric(event, metric="volume")

    @staticmethod
    def _event_liquidity(event: dict[str, Any]) -> float:
        for key in ("liquidity", "liquidityUSD", "liquidityNum"):
            value = GammaHttpCatalog._to_float(event.get(key))
            if value is not None:
                return value
        return GammaHttpCatalog._sum_market_metric(event, metric="liquidity")

    @staticmethod
    def _sum_market_metric(event: dict[str, Any], metric: str) -> float:
        markets_raw = event.get("markets") or []
        if not isinstance(markets_raw, list):
            return 0.0
        total = 0.0
        for item in markets_raw:
            if not isinstance(item, dict):
                continue
            if metric == "volume":
                value = GammaHttpCatalog._to_float(
                    item.get("volume_24h")
                    or item.get("volume24h")
                    or item.get("volume24hr")
                    or item.get("volume24hrClob")
                )
            elif metric == "liquidity":
                value = GammaHttpCatalog._to_float(
                    item.get("liquidity") or item.get("liquidityUSD") or item.get("liquidityNum")
                )
            else:
                value = None
            if value is None:
                continue
            total += value
        return total

    @staticmethod
    def _extract_markets_from_event(event: dict[str, Any]) -> list[Market]:
        markets_raw = event.get("markets") or []
        if not isinstance(markets_raw, list):
            return []
        event_id = str(event.get("id") or event.get("event_id") or event.get("eventId") or "")
        event_title = event.get("title") or event.get("slug") or ""
        event_end = event.get("end_ts") or event.get("endDate") or event.get("endDateIso")
        event_enable_ob = event.get("enableOrderBook")
        enriched: list[dict[str, Any]] = []
        for item in markets_raw:
            if not isinstance(item, dict):
                continue
            if event_id and "event_id" not in item and "eventId" not in item:
                item["_event_id"] = event_id
            if event_end is not None and not any(
                key in item for key in ("end_ts", "endDate", "endDateIso")
            ):
                item["endDate"] = event_end
            if event_enable_ob is not None and "enableOrderBook" not in item:
                item["enableOrderBook"] = event_enable_ob
            enriched.append(item)
        markets = [GammaHttpCatalog._parse_market(item) for item in enriched]
        for market in markets:
            if not market.question:
                market.question = event_title
        return markets

    @staticmethod
    def _parse_market(raw: dict[str, Any]) -> Market:
        market_id = str(
            raw.get("conditionId")
            or raw.get("condition_id")
            or raw.get("id")
            or raw.get("market_id")
            or raw.get("marketId")
            or ""
        )
        question = raw.get("question") or raw.get("title") or raw.get("description") or ""
        event_id = str(raw.get("_event_id") or raw.get("event_id") or raw.get("eventId") or "")
        active = GammaHttpCatalog._to_bool(raw.get("active"), default=True)
        closed = GammaHttpCatalog._to_bool(raw.get("closed"), default=False)
        resolved = GammaHttpCatalog._to_bool(raw.get("resolved"), default=False)
        enable_orderbook_raw = raw.get("enableOrderBook") or raw.get("enable_orderbook")
        enable_orderbook = (
            None
            if enable_orderbook_raw is None
            else GammaHttpCatalog._to_bool(enable_orderbook_raw, default=True)
        )
        end_ts = GammaHttpCatalog._parse_end_ts(
            raw.get("end_ts") or raw.get("endDate") or raw.get("endDateIso")
        )
        liquidity = GammaHttpCatalog._to_float(
            raw.get("liquidity") or raw.get("liquidityUSD") or raw.get("liquidityNum")
        )
        volume_24h = GammaHttpCatalog._to_float(
            raw.get("volume_24h")
            or raw.get("volume24h")
            or raw.get("volume24hr")
            or raw.get("volume24hrClob")
        )

        clob_token_ids = GammaHttpCatalog._parse_clob_token_ids(raw.get("clobTokenIds"))
        outcomes = GammaHttpCatalog._extract_outcomes(raw)
        outcomes = GammaHttpCatalog._attach_outcome_token_ids(outcomes, clob_token_ids)
        token_ids = clob_token_ids + [outcome.token_id for outcome in outcomes if outcome.token_id]
        token_ids = [token_id for token_id in dict.fromkeys(token_ids) if token_id]

        return Market(
            market_id=market_id,
            question=question,
            event_id=event_id or None,
            enable_orderbook=enable_orderbook,
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
    def _event_is_active(event: dict[str, Any]) -> bool:
        active = GammaHttpCatalog._to_bool(event.get("active"), default=True)
        closed = GammaHttpCatalog._to_bool(event.get("closed"), default=False)
        archived = GammaHttpCatalog._to_bool(event.get("archived"), default=False)
        if not active or closed or archived:
            return False
        pending = GammaHttpCatalog._to_bool(event.get("pendingDeployment"), default=False)
        deploying = GammaHttpCatalog._to_bool(event.get("deploying"), default=False)
        return not (pending or deploying)

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
                    return int(dt.astimezone(UTC).timestamp() * 1000)
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
    def _to_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return default

    @staticmethod
    def _extract_outcomes(raw: dict[str, Any]) -> list[OutcomeToken]:
        outcomes: list[OutcomeToken] = []

        def add_token(token_raw: dict[str, Any]) -> None:
            token_id = GammaHttpCatalog._coerce_token_id(token_raw)
            side = token_raw.get("side") or token_raw.get("name") or token_raw.get("title")
            if token_id:
                outcomes.append(OutcomeToken(token_id=token_id, side=side, raw=token_raw))

        outcomes_raw = raw.get("outcomes")
        if isinstance(outcomes_raw, str):
            try:
                outcomes_raw = json.loads(outcomes_raw)
            except json.JSONDecodeError:
                outcomes_raw = [item.strip() for item in outcomes_raw.split(",") if item.strip()]

        if isinstance(outcomes_raw, list):
            for outcome in outcomes_raw:
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
    def _attach_outcome_token_ids(
        outcomes: list[OutcomeToken],
        clob_token_ids: list[str],
    ) -> list[OutcomeToken]:
        if not outcomes or not clob_token_ids:
            return outcomes
        if len(outcomes) != len(clob_token_ids):
            return outcomes

        enriched: list[OutcomeToken] = []
        for idx, outcome in enumerate(outcomes):
            token_id = outcome.token_id or clob_token_ids[idx]
            enriched.append(
                OutcomeToken(
                    token_id=token_id,
                    side=outcome.side,
                    raw=outcome.raw,
                )
            )
        return enriched

    @staticmethod
    def _parse_clob_token_ids(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed if item]
                except json.JSONDecodeError:
                    pass
            if "," in text:
                return [item.strip() for item in text.split(",") if item.strip()]
            return [text]
        return []

    @staticmethod
    def _coerce_token_id(token_raw: dict[str, Any]) -> str | None:
        for key in ("token_id", "tokenId", "clobTokenId", "asset_id", "assetId", "id"):
            if key in token_raw and token_raw[key] is not None:
                return str(token_raw[key])
        return None
