from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import logging
import os
from threading import Lock
import time
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4


LOGGER = logging.getLogger(__name__)
PROVIDER_ID = "feishu_bitable"
DEFAULT_FIELD_MAP = {
    "title": "项目标题",
    "source_name": "来源网站",
    "published_at": "发布时间",
    "source_url": "原文链接",
    "summary": "核心摘要",
    "word_url": "Word下载地址",
    "query": "检索任务",
    "task_id": "定时任务ID",
    "run_id": "运行ID",
    "collected_at": "抓取时间",
    "change_type": "变更类型",
    "project_id": "项目ID",
    "delivery_fingerprint": "交付指纹",
}


class FeishuError(RuntimeError):
    pass


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 15,
    ) -> dict[str, Any]: ...


class UrllibJsonTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 15,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            **(headers or {}),
        }
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            raise FeishuError(f"Feishu HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise FeishuError(f"Feishu network error: {error}") from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise FeishuError("Feishu returned non-JSON content") from error
        if not isinstance(result, dict):
            raise FeishuError("Feishu returned an invalid JSON object")
        return result


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str = ""
    app_secret: str = ""
    app_token: str = ""
    table_id: str = ""
    public_base_url: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""
    table_url: str = ""
    api_base_url: str = "https://open.feishu.cn"
    timeout_seconds: float = 15
    max_attempts: int = 10
    field_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAP))
    enabled_setting: str = "auto"

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        field_map = dict(DEFAULT_FIELD_MAP)
        raw_field_map = os.environ.get("BIDRADAR_FEISHU_FIELD_MAP_JSON", "").strip()
        if raw_field_map:
            try:
                override = json.loads(raw_field_map)
            except json.JSONDecodeError as error:
                raise FeishuError("BIDRADAR_FEISHU_FIELD_MAP_JSON is not valid JSON") from error
            if not isinstance(override, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in override.items()
            ):
                raise FeishuError("BIDRADAR_FEISHU_FIELD_MAP_JSON must be a string map")
            field_map.update(override)
        return cls(
            app_id=os.environ.get("BIDRADAR_FEISHU_APP_ID", "").strip(),
            app_secret=os.environ.get("BIDRADAR_FEISHU_APP_SECRET", "").strip(),
            app_token=os.environ.get("BIDRADAR_FEISHU_APP_TOKEN", "").strip(),
            table_id=os.environ.get("BIDRADAR_FEISHU_TABLE_ID", "").strip(),
            public_base_url=os.environ.get("BIDRADAR_PUBLIC_BASE_URL", "").strip(),
            webhook_url=os.environ.get("BIDRADAR_FEISHU_WEBHOOK_URL", "").strip(),
            webhook_secret=os.environ.get("BIDRADAR_FEISHU_WEBHOOK_SECRET", "").strip(),
            table_url=os.environ.get("BIDRADAR_FEISHU_TABLE_URL", "").strip(),
            api_base_url=os.environ.get(
                "BIDRADAR_FEISHU_API_BASE_URL", "https://open.feishu.cn"
            ).strip().rstrip("/"),
            timeout_seconds=float(os.environ.get("BIDRADAR_FEISHU_TIMEOUT_SECONDS", "15")),
            max_attempts=int(os.environ.get("BIDRADAR_FEISHU_MAX_ATTEMPTS", "10")),
            field_map=field_map,
            enabled_setting=os.environ.get("BIDRADAR_FEISHU_ENABLED", "auto").strip().lower(),
        )

    @property
    def missing_settings(self) -> list[str]:
        required = {
            "BIDRADAR_FEISHU_APP_ID": self.app_id,
            "BIDRADAR_FEISHU_APP_SECRET": self.app_secret,
            "BIDRADAR_FEISHU_APP_TOKEN": self.app_token,
            "BIDRADAR_FEISHU_TABLE_ID": self.table_id,
            "BIDRADAR_PUBLIC_BASE_URL": self.public_base_url,
        }
        return [name for name, value in required.items() if not value]

    @property
    def enabled(self) -> bool:
        if self.enabled_setting in {"0", "false", "off", "disabled"}:
            return False
        if self.enabled_setting in {"1", "true", "on", "enabled"}:
            return not self.missing_settings
        return not self.missing_settings

    def safe_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": not self.missing_settings,
            "missing_settings": self.missing_settings,
            "app_id": self._mask(self.app_id),
            "app_token": self._mask(self.app_token),
            "table_id": self._mask(self.table_id),
            "public_base_url": self.public_base_url,
            "webhook_configured": bool(self.webhook_url),
        }

    @staticmethod
    def _mask(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}…{value[-4:]}"


class FeishuBitableClient:
    def __init__(
        self,
        config: FeishuConfig,
        *,
        transport: JsonTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.transport = transport or UrllibJsonTransport()
        self.clock = clock
        self._token = ""
        self._token_expires_at = 0.0
        self._token_lock = Lock()
        self._validated_fields = False

    def tenant_access_token(self) -> str:
        with self._token_lock:
            now = float(self.clock())
            if self._token and now < self._token_expires_at:
                return self._token
            response = self.transport.request(
                "POST",
                f"{self.config.api_base_url}/open-apis/auth/v3/tenant_access_token/internal",
                payload={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
                timeout=self.config.timeout_seconds,
            )
            self._ensure_success(response, "tenant token")
            token = str(response.get("tenant_access_token") or "")
            if not token:
                raise FeishuError("Feishu token response did not contain tenant_access_token")
            expire = max(60, int(response.get("expire") or 7200))
            self._token = token
            self._token_expires_at = now + expire - 60
            return token

    def list_fields(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            query = {"page_size": 100}
            if page_token:
                query["page_token"] = page_token
            response = self._authorized_request(
                "GET",
                self._table_endpoint("fields") + "?" + urlencode(query),
            )
            data = response.get("data") or {}
            items.extend(
                item for item in (data.get("items") or []) if isinstance(item, dict)
            )
            next_token = str(data.get("page_token") or "")
            if not data.get("has_more") or not next_token or next_token == page_token:
                return items
            page_token = next_token

    def validate_fields(self) -> None:
        if self._validated_fields:
            return
        available = {
            str(item.get("field_name"))
            for item in self.list_fields()
            if item.get("field_name")
        }
        required = set(self.config.field_map.values())
        missing = sorted(required.difference(available))
        if missing:
            raise FeishuError(
                "Feishu Bitable is missing required fields: " + ", ".join(missing)
            )
        self._validated_fields = True

    def batch_create_records(self, logical_rows: list[dict[str, Any]]) -> list[str]:
        if not logical_rows:
            return []
        self.validate_fields()
        records = [
            {
                "fields": {
                    self.config.field_map[key]: value
                    for key, value in row.items()
                    if key in self.config.field_map and value not in {None, ""}
                }
            }
            for row in logical_rows
        ]
        response = self._authorized_request(
            "POST",
            self._table_endpoint("records/batch_create"),
            payload={"records": records},
        )
        created = (response.get("data") or {}).get("records") or []
        return [
            str(item.get("record_id") or "")
            for item in created
            if isinstance(item, dict)
        ]

    def send_webhook(self, *, delivered_count: int, query: str) -> None:
        if not self.config.webhook_url:
            return
        timestamp = str(int(time.time()))
        payload: dict[str, Any] = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "BidRadar-X 定时抓取更新",
                        "content": [[
                            {
                                "tag": "text",
                                "text": f"{query}：新增或变化 {delivered_count} 个项目，已写入企业多维表格。",
                            },
                            *(
                                [{"tag": "a", "text": "打开多维表格", "href": self.config.table_url}]
                                if self.config.table_url
                                else []
                            ),
                        ]],
                    }
                }
            },
        }
        if self.config.webhook_secret:
            string_to_sign = f"{timestamp}\n{self.config.webhook_secret}"
            digest = hmac.new(
                string_to_sign.encode("utf-8"), digestmod=sha256
            ).digest()
            payload.update({"timestamp": timestamp, "sign": base64.b64encode(digest).decode()})
        response = self.transport.request(
            "POST",
            self.config.webhook_url,
            payload=payload,
            timeout=self.config.timeout_seconds,
        )
        code = response.get("code", response.get("StatusCode", 0))
        if code not in {0, "0", None}:
            raise FeishuError(f"Feishu webhook rejected the message: {response}")

    def _authorized_request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.transport.request(
            method,
            url,
            headers={"Authorization": f"Bearer {self.tenant_access_token()}"},
            payload=payload,
            timeout=self.config.timeout_seconds,
        )
        self._ensure_success(response, "Bitable")
        return response

    def _table_endpoint(self, suffix: str) -> str:
        app_token = quote(self.config.app_token, safe="")
        table_id = quote(self.config.table_id, safe="")
        return (
            f"{self.config.api_base_url}/open-apis/bitable/v1/apps/{app_token}"
            f"/tables/{table_id}/{suffix}"
        )

    @staticmethod
    def _ensure_success(response: dict[str, Any], operation: str) -> None:
        code = response.get("code", 0)
        if code not in {0, "0", None}:
            message = response.get("msg") or response.get("message") or "unknown error"
            raise FeishuError(f"Feishu {operation} failed ({code}): {message}")


class FeishuDeliveryService:
    """Transactional outbox producer and serial Bitable dispatcher."""

    _flush_lock = Lock()

    def __init__(
        self,
        repository: Any,
        *,
        config: FeishuConfig | None = None,
        client: FeishuBitableClient | None = None,
        worker_id: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or FeishuConfig.from_env()
        self.client = client or FeishuBitableClient(self.config)
        self.worker_id = worker_id or f"feishu-{uuid4()}"
        self.now = now or (lambda: datetime.now(timezone.utc))

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def prepare_events(
        self,
        *,
        result: dict[str, Any],
        task_id: str,
        run_id: str,
        query: str,
        collected_at: datetime,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        changes = {
            str(item.get("project_id")): item
            for item in result.get("changes", [])
            if isinstance(item, dict) and item.get("project_id")
        }
        report = result.get("report") or {}
        if not changes or report.get("status") != "generated":
            return []
        documents = {
            str(item.get("project_id")): item
            for item in report.get("documents", [])
            if isinstance(item, dict) and item.get("project_id")
        }
        delivery_fingerprint = str(report.get("delivery_fingerprint") or run_id)
        events: list[dict[str, Any]] = []
        for project in result.get("projects", []):
            project_id = str(project.get("project_id") or "")
            if project_id not in changes:
                continue
            primary = self._primary_notice(project)
            source = primary.get("source") or {}
            document = documents.get(project_id, {})
            download_path = str(document.get("download_url") or "")
            word_url = (
                urljoin(self.config.public_base_url.rstrip("/") + "/", download_path.lstrip("/"))
                if download_path
                else ""
            )
            payload = {
                "title": str(primary.get("title") or project.get("title") or "未命名项目"),
                "source_name": str(source.get("source_name") or "来源未标注"),
                "published_at": str(primary.get("published_at") or ""),
                "source_url": str(source.get("source_url") or ""),
                "summary": str(primary.get("core_content") or "")[:2000],
                "word_url": word_url,
                "query": query,
                "task_id": task_id,
                "run_id": run_id,
                "collected_at": collected_at.astimezone().isoformat(timespec="seconds"),
                "change_type": str(changes[project_id].get("type") or "material_change"),
                "project_id": project_id,
                "delivery_fingerprint": delivery_fingerprint,
            }
            idempotency_key = sha256(
                f"{PROVIDER_ID}\0{delivery_fingerprint}\0{project_id}".encode("utf-8")
            ).hexdigest()
            events.append({
                "event_id": idempotency_key,
                "provider": PROVIDER_ID,
                "idempotency_key": idempotency_key,
                "payload": payload,
                "max_attempts": self.config.max_attempts,
            })
        return events

    def flush_due(self, *, limit: int = 100) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "delivered": 0, **self.config.safe_status()}
        if not self._flush_lock.acquire(blocking=False):
            return {"status": "busy", "delivered": 0}
        try:
            claimed = self.repository.claim_external_deliveries(
                provider=PROVIDER_ID,
                worker_id=self.worker_id,
                now=self.now(),
                lease_duration=timedelta(minutes=2),
                limit=limit,
            )
            if not claimed:
                return {"status": "idle", "delivered": 0}
            delivered = 0
            failed = 0
            for chunk_start in range(0, len(claimed), 20):
                chunk = claimed[chunk_start:chunk_start + 20]
                try:
                    delivered += self._deliver_chunk(chunk)
                except Exception as batch_error:
                    LOGGER.warning("Feishu batch delivery failed; isolating rows: %s", batch_error)
                    if len(chunk) == 1:
                        failed += 1
                        self.repository.mark_external_deliveries_retry(
                            event_ids=[chunk[0]["event_id"]],
                            worker_id=self.worker_id,
                            now=self.now(),
                            error=f"{type(batch_error).__name__}: {batch_error}",
                        )
                        continue
                    for item in chunk:
                        try:
                            delivered += self._deliver_chunk([item])
                        except Exception as item_error:
                            failed += 1
                            self.repository.mark_external_deliveries_retry(
                                event_ids=[item["event_id"]],
                                worker_id=self.worker_id,
                                now=self.now(),
                                error=f"{type(item_error).__name__}: {item_error}",
                            )
            if delivered:
                try:
                    self.client.send_webhook(
                        delivered_count=delivered,
                        query=str(claimed[0]["payload"].get("query") or "定时检索"),
                    )
                except Exception as error:
                    LOGGER.warning("Feishu Bitable succeeded but webhook failed: %s", error)
            return {"status": "completed", "delivered": delivered, "failed": failed}
        finally:
            self._flush_lock.release()

    def _deliver_chunk(self, items: list[dict[str, Any]]) -> int:
        record_ids = self.client.batch_create_records([item["payload"] for item in items])
        self.repository.mark_external_deliveries_delivered(
            event_ids=[item["event_id"] for item in items],
            worker_id=self.worker_id,
            now=self.now(),
            remote_record_ids=record_ids,
        )
        return len(items)

    @staticmethod
    def _primary_notice(project: dict[str, Any]) -> dict[str, Any]:
        notices = [
            document.get("notice")
            for document in project.get("documents", [])
            if isinstance(document, dict) and isinstance(document.get("notice"), dict)
        ]
        return max(
            notices,
            key=lambda notice: (
                (notice.get("source") or {}).get("authority") or 0,
                notice.get("published_at") or "",
            ),
            default={},
        )
