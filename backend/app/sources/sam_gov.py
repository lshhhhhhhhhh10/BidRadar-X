"""Authenticated SAM.gov contract-opportunity source.

SAM.gov exposes a documented public Opportunities API.  A registered user must
generate an API key in SAM.gov Account Details; the key is kept server-side and
is never returned by BidRadar-X.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas.tender import SourceRecord, TaskSpec, TenderNotice


API_KEY_ENV = "BIDRADAR_SAM_GOV_API_KEY"
SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class SAMGovSourceError(RuntimeError):
    """Base error for SAM.gov collection."""


class SAMGovAuthenticationError(SAMGovSourceError):
    """The server-side SAM.gov API key is missing or rejected."""


class SAMGovResponseError(SAMGovSourceError):
    """SAM.gov returned an unusable response."""


@dataclass(frozen=True)
class SAMGovHTTPResponse:
    url: str
    status_code: int
    payload: Mapping[str, Any]


class SAMGovTransport(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int],
        timeout: float,
    ) -> SAMGovHTTPResponse:
        ...


class _UrllibTransport:
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int],
        timeout: float,
    ) -> SAMGovHTTPResponse:
        return await asyncio.to_thread(
            self._get_sync,
            url,
            params=params,
            timeout=timeout,
        )

    @staticmethod
    def _get_sync(
        url: str,
        *,
        params: Mapping[str, str | int],
        timeout: float,
    ) -> SAMGovHTTPResponse:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BidRadar-X/0.1 (SAM.gov public API client)",
            },
            method="GET",
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise SAMGovResponseError("SAM.gov response exceeded 10 MB")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise SAMGovResponseError("SAM.gov response was not valid JSON") from error
            if not isinstance(payload, Mapping):
                raise SAMGovResponseError("SAM.gov response root was not an object")
            return SAMGovHTTPResponse(
                url=response.geturl(),
                status_code=response.status,
                payload=payload,
            )


class SAMGovSource:
    """Collect published opportunities through SAM.gov's authenticated API."""

    metadata = {
        "source_id": "sam-gov",
        "name": "SAM.gov Contract Opportunities",
        "authority": 1.0,
        "hit_rate": 0.42,
        "stability": 0.92,
        "cost": 0.35,
        "attempts": 0,
        "requires_login": True,
        "credential_env": API_KEY_ENV,
        "authentication_mode": "registered-user-api-key",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: SAMGovTransport | None = None,
        timeout: float = 20.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._api_key = (api_key or "").strip()
        self._transport = transport or _UrllibTransport()
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> SAMGovSource:
        values = os.environ if environment is None else environment
        return cls(api_key=values.get(API_KEY_ENV), **kwargs)

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def collect(
        self,
        task_spec: TaskSpec | Mapping[str, Any],
        search_plan: Mapping[str, Any] | None = None,
    ) -> list[TenderNotice]:
        if not self._api_key:
            raise SAMGovAuthenticationError(
                f"missing {API_KEY_ENV}; generate a personal API key in SAM.gov Account Details"
            )

        task = (
            task_spec
            if isinstance(task_spec, TaskSpec)
            else TaskSpec.model_validate(dict(task_spec))
        )
        plan = dict(search_plan or {})
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")

        start = task.time_range_start or (now - timedelta(days=30))
        end = task.time_range_end or now
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        if end_utc - start_utc > timedelta(days=365):
            start_utc = end_utc - timedelta(days=365)

        params: dict[str, str | int] = {
            "api_key": self._api_key,
            "postedFrom": start_utc.strftime("%m/%d/%Y"),
            "postedTo": end_utc.strftime("%m/%d/%Y"),
            "limit": min(max(int(plan.get("sam_gov_limit", 20)), 1), 100),
            "offset": 0,
        }
        query = str(plan.get("query") or task.topic).strip()
        if query:
            params["title"] = query

        try:
            response = await self._transport.get(
                SEARCH_URL,
                params=params,
                timeout=self._timeout,
            )
        except SAMGovSourceError:
            raise
        except Exception as error:
            raise SAMGovSourceError("SAM.gov request failed") from error

        if response.status_code in {401, 403}:
            raise SAMGovAuthenticationError("SAM.gov rejected the configured API key")
        if response.status_code != 200:
            raise SAMGovResponseError(f"SAM.gov returned HTTP {response.status_code}")

        records = response.payload.get("opportunitiesData", [])
        if not isinstance(records, list):
            raise SAMGovResponseError("SAM.gov response had no opportunitiesData list")

        fetched_at = now.astimezone(timezone.utc)
        notices: list[TenderNotice] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            notice = self._to_notice(record, fetched_at=fetched_at)
            if notice is not None:
                notices.append(notice)
        return notices

    def _to_notice(
        self,
        record: Mapping[str, Any],
        *,
        fetched_at: datetime,
    ) -> TenderNotice | None:
        notice_id = _clean(record.get("noticeId"))
        title = _clean(record.get("title"))
        posted_at = _parse_date(record.get("postedDate"))
        if not notice_id or not title or posted_at is None:
            return None

        description = _clean(record.get("description"))
        organization = _clean(
            record.get("fullParentPathName")
            or record.get("department")
            or record.get("office")
        )
        notice_kind = _clean(record.get("type"))
        content_parts = [title]
        if description and description.casefold() not in {"null", "none"}:
            content_parts.append(description)
        if organization:
            content_parts.append(f"Contracting organization: {organization}")
        if notice_kind:
            content_parts.append(f"Notice type: {notice_kind}")
        core_content = "\n".join(content_parts)

        ui_link = _clean(record.get("uiLink"))
        if not ui_link.startswith("https://"):
            ui_link = f"https://sam.gov/opp/{notice_id}/view"
        raw_payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        raw_fingerprint = _fingerprint(raw_payload)
        notice_fingerprint = _fingerprint(notice_id, notice_kind, posted_at.isoformat())
        solicitation_number = _clean(record.get("solicitationNumber"))
        project_fingerprint = _fingerprint(solicitation_number or title, organization)

        return TenderNotice(
            notice_id=f"sam-{notice_id}",
            notice_type="award" if "award" in notice_kind.casefold() else "tender",
            title=title,
            published_at=posted_at,
            source=SourceRecord(
                source_id=self.metadata["source_id"],
                source_name=self.metadata["name"],
                source_url=ui_link,
                publication_role="original",
                source_notice_id=notice_id,
                authority=self.metadata["authority"],
            ),
            core_content=core_content,
            raw_content_fingerprint=raw_fingerprint,
            notice_stable_fingerprint=notice_fingerprint,
            project_stable_fingerprint=project_fingerprint,
            fetched_at=fetched_at,
        )


def _parse_date(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _fingerprint(*values: str) -> str:
    return sha256("|".join(values).encode("utf-8")).hexdigest()


__all__ = [
    "API_KEY_ENV",
    "SAMGovAuthenticationError",
    "SAMGovHTTPResponse",
    "SAMGovResponseError",
    "SAMGovSource",
    "SAMGovSourceError",
]
