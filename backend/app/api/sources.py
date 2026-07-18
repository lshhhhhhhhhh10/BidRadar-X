from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from ..sources.tianyancha import TOKEN_ENV
from ..services.spend_guard import DailySpendGuard


router = APIRouter(prefix="/api/sources", tags=["sources"])

_CREDENTIAL_ENV_BY_SOURCE = {
    "tianyancha-bids": TOKEN_ENV,
}


class SourceCredentialInput(BaseModel):
    credential: SecretStr


class SpendLimitInput(BaseModel):
    daily_limit: Decimal = Field(ge=0, le=1_000_000)


def _masked(value: str) -> str:
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}••••{value[-4:]}"


@router.get("/budget")
def get_spend_budget() -> dict[str, object]:
    return DailySpendGuard().snapshot().as_dict()


@router.put("/budget")
def set_spend_budget(payload: SpendLimitInput) -> dict[str, object]:
    return DailySpendGuard().set_daily_limit(payload.daily_limit).as_dict()


@router.put("/{source_id}/credential")
def set_source_credential(source_id: str, payload: SourceCredentialInput) -> dict[str, object]:
    """Load one local user's credential into this backend process only."""

    env_name = _CREDENTIAL_ENV_BY_SOURCE.get(source_id)
    if env_name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该来源不支持凭据连接。")
    credential = payload.credential.get_secret_value().strip()
    if not 8 <= len(credential) <= 512:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="凭据长度应为 8 至 512 个字符。")
    os.environ[env_name] = credential
    return {
        "source_id": source_id,
        "configured": True,
        "masked_credential": _masked(credential),
        "storage": "process_memory",
        "verified": False,
    }


@router.delete("/{source_id}/credential")
def clear_source_credential(source_id: str) -> dict[str, object]:
    env_name = _CREDENTIAL_ENV_BY_SOURCE.get(source_id)
    if env_name is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该来源不支持凭据连接。")
    os.environ.pop(env_name, None)
    return {"source_id": source_id, "configured": False}


@router.get("")
def list_sources() -> dict[str, list[dict[str, object]]]:
    tianyancha_ready = bool(os.environ.get(TOKEN_ENV, "").strip())
    return {
        "items": [
            {
                "id": "ccgp",
                "name": "中国政府采购网",
                "category": "government",
                "category_label": "政府 / 公共平台",
                "url": "https://www.ccgp.gov.cn/",
                "host": "ccgp.gov.cn",
                "requires_auth": False,
                "status": "ready",
                "status_label": "已接入 · 可采集",
                "detail": "财政部政府采购公告正式来源，已接入生产工作流。",
                "collection_mode": "公开网页",
            },
            {
                "id": "cmcc-b2b",
                "name": "中国移动采购与招标网",
                "category": "enterprise",
                "category_label": "企业官网 / 行业协会",
                "url": "https://b2b.10086.cn/",
                "host": "b2b.10086.cn",
                "requires_auth": False,
                "status": "ready",
                "status_label": "公开公告 API · 可采集",
                "detail": "已接入官网公开白名单接口，可检索公告、读取正文并归档公告内嵌 PDF；供应商业务区登录与公开采集相互独立。",
                "collection_mode": "公开公告列表 + 详情 PDF",
            },
            {
                "id": "tianyancha-bids",
                "name": "天眼查开放平台 · 招投标搜索",
                "category": "commercial",
                "category_label": "商业聚合网站",
                "url": "https://open.tianyancha.com/open/1063",
                "host": "open.tianyancha.com",
                "requires_auth": True,
                "status": "ready" if tianyancha_ready else "needs_auth",
                "status_label": "Token 已配置 · 可采集" if tianyancha_ready else "登录申请 Token",
                "detail": (
                    "服务端已读取开放平台 Token，招投标搜索 API 已加入来源路由。"
                    if tianyancha_ready
                    else "登录开放平台并申请接口 1063，在数据中心的“我的接口”获取 Token。"
                ),
                "collection_mode": "开放平台 API 1063 · 约 ¥0.2/次",
            },
            {
                "id": "ted-eu",
                "name": "TED · 欧盟招标公告",
                "category": "overseas",
                "category_label": "海外采购 / 招标平台",
                "url": "https://ted.europa.eu/",
                "host": "ted.europa.eu",
                "requires_auth": False,
                "status": "ready",
                "status_label": "官方 API · 可采集",
                "detail": "欧盟出版局公开 Search API，允许匿名检索和公告复用。",
                "collection_mode": "TED Search API v3",
            },
            {
                "id": "ctba-news",
                "name": "中国招标投标协会",
                "category": "news",
                "category_label": "新闻 / 行业资讯",
                "url": "https://www.ctba.org.cn/",
                "host": "ctba.org.cn",
                "requires_auth": False,
                "status": "ready",
                "status_label": "公开资讯 · 可采集",
                "detail": "行业政策、标准、培训及招标投标行业动态公开来源。",
                "collection_mode": "公开资讯页",
            },
        ]
    }
