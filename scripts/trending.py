#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""today-trending — 微博 / 抖音 / 百度 热搜一键拉取

容错策略:条目级容错优先(脏行跳过,回落 0),平台级失败才整体标 failed。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from curl_cffi.requests import AsyncSession
from lxml import etree  # noqa: F401  (保留:百度解析虽已切 s-data,此处占位以免误删依赖)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)
PLATFORMS = ("weibo", "douyin", "baidu")

URL_TEMPLATES = {
    "weibo":  "https://s.weibo.com/weibo?q={}",
    "douyin": "https://www.douyin.com/search?keyword={}",
    "baidu":  "https://www.baidu.com/s?wd={}",
}

# 抖音 billboard 的 label 是数字枚举,映射成可读角标
DOUYIN_LABELS = {1: "新", 3: "爆", 8: "首发", 10: "热"}

class TrendingError(Exception):
    """抓取/解析失败,异常信息必须写明平台 + 具体原因"""


# ---------- 条目级容错 ----------

def _safe_int(value, default: int = 0) -> int:
    """任何脏值都回落 default,不抛异常。None / bool / '' / 'abc' / 列表都安全。"""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clean_word(value) -> str:
    """清洗热搜词:非字符串 / 空 / 超长(>100,多为脏数据)一律丢弃。"""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned or len(cleaned) > 100:
        return ""
    return cleaned


def _clean_desc(value, limit: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:limit] if len(cleaned) > limit else cleaned


def _entry(word, raw_hot, board_rank=None, icon_desc=None, desc="") -> dict | None:
    """构造一条记录;词不合法返回 None,由调用方跳过。热度脏值回落 0。"""
    cleaned = _clean_word(word)
    if not cleaned:
        return None
    return {
        "word": cleaned,
        "hot_value": round(_safe_int(raw_hot, 0) / 10000, 2),
        "board_rank": board_rank,
        "icon_desc": _clean_word(icon_desc) or None,
        "desc": _clean_desc(desc),
    }


# ---------- 抓取 ----------

async def fetch_weibo(session: AsyncSession, top: int) -> list[dict]:
    headers = {
        "referer": "https://weibo.com/hot/search",
        "user-agent": USER_AGENT,
        "x-requested-with": "XMLHttpRequest",
    }
    resp = await session.get("https://weibo.com/ajax/side/hotSearch", headers=headers)
    try:
        data = resp.json()
    except Exception as exc:
        raise TrendingError(f"weibo: 响应非 JSON (status={resp.status_code}): {exc}") from exc

    if not isinstance(data, dict):
        raise TrendingError(f"weibo: 顶层不是对象,实际 {type(data).__name__}")
    if data.get("ok") not in (1, True):
        raise TrendingError(f"weibo: 接口未返回 ok=1,实际 ok={data.get('ok')!r}")

    realtime = (data.get("data") or {}).get("realtime")
    if realtime is None:
        raise TrendingError("weibo: data.realtime 为 null(通常是风控拦截或需登录态)")
    if not isinstance(realtime, list):
        raise TrendingError(f"weibo: data.realtime 类型异常:{type(realtime).__name__}")

    out = []
    for item in realtime:
        if not isinstance(item, dict):
            continue  # 脏行跳过
        row = _entry(
            item.get("word"),
            item.get("num"),
            board_rank=_safe_int(item.get("realpos"), None),
            icon_desc=item.get("icon_desc"),
        )
        if row:
            out.append(row)
    return out[:top]


async def fetch_douyin(session: AsyncSession, top: int) -> list[dict]:
    url = "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"
    resp = await session.get(url, headers={"user-agent": USER_AGENT})
    try:
        data = resp.json()
    except Exception as exc:
        raise TrendingError(f"douyin: 响应非 JSON (status={resp.status_code}): {exc}") from exc

    if not isinstance(data, dict):
        raise TrendingError(f"douyin: 顶层不是对象,实际 {type(data).__name__}")

    word_list = data.get("word_list")
    if word_list is None:
        raise TrendingError("douyin: word_list 缺失(端点可能已下线或需签名参数)")
    if not isinstance(word_list, list):
        raise TrendingError(f"douyin: word_list 类型异常:{type(word_list).__name__}")

    out = []
    for idx, item in enumerate(word_list, 1):
        if not isinstance(item, dict):
            continue
        row = _entry(
            item.get("word"),
            item.get("hot_value"),
            board_rank=idx,
            icon_desc=DOUYIN_LABELS.get(_safe_int(item.get("label"), 0)),
        )
        if row:
            out.append(row)
    return out[:top]


async def fetch_baidu(session: AsyncSession, top: int) -> list[dict]:
    """解析页面内嵌 <!--s-data:{...}--> JSON;XPath 版本已废弃(6 层路径极脆弱)。"""
    url = "https://top.baidu.com/board?tab=realtime"
    text = (await session.get(url, headers={"user-agent": USER_AGENT})).text

    match = re.search(r"<!--s-data:(.*?)-->", text, re.S)
    if not match:
        raise TrendingError("baidu: 页面未找到 <!--s-data:...--> 内嵌 JSON(页面结构已改版)")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise TrendingError(f"baidu: s-data JSON 解析失败:{exc}") from exc

    cards = ((data or {}).get("data") or {}).get("cards")
    if not isinstance(cards, list) or not cards:
        raise TrendingError("baidu: data.cards 缺失或为空")
    content = cards[0].get("content")
    if not isinstance(content, list):
        raise TrendingError(f"baidu: cards[0].content 类型异常:{type(content).__name__}")

    out = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("isTop"):
            continue  # 剔除置顶项(与 topContent 重复)
        # 百度 index 是 0-based,+1 归一为 1-based
        index = _safe_int(item.get("index"), None)
        row = _entry(
            item.get("word"),
            item.get("hotScore"),
            board_rank=index + 1 if index is not None else None,
            desc=item.get("desc"),
        )
        if row:
            out.append(row)
    return out[:top]


FETCHERS = {"weibo": fetch_weibo, "douyin": fetch_douyin, "baidu": fetch_baidu}


def url_for(platform: str, word: str) -> str:
    return URL_TEMPLATES[platform].format(urllib.parse.quote(word, safe=""))


async def fetch_all(only: str | None = None, top: int = 10) -> tuple[dict, dict]:
    """返回 (items_by_platform, status_by_platform)。status 只覆盖被请求的平台。"""
    targets = [only] if only else list(PLATFORMS)
    results: dict[str, list[dict]] = {}
    status: dict[str, str] = {}

    # 所有平台共用一个 session:复用 TLS 指纹 & 连接池
    async with AsyncSession(impersonate="chrome", timeout=20) as session:

        async def run(name: str):
            try:
                return name, await FETCHERS[name](session, top)
            except TrendingError as exc:
                print(f"❌ {exc}", file=sys.stderr)
                return name, []
            except Exception as exc:  # 兜底:未知异常也必须带平台名
                print(f"❌ {name}: 未预期异常 {type(exc).__name__}: {exc}", file=sys.stderr)
                return name, []

        for name, items in await asyncio.gather(*(run(n) for n in targets)):
            results[name] = items
            status[name] = "ok" if items else "failed"

    return results, status


# ---------- CLI ----------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="微博 / 抖音 / 百度 热搜一键拉取")
    parser.add_argument("--platform", choices=PLATFORMS,
                        help="只抓一个平台;不传则三平台并发")
    parser.add_argument("--top", type=int, default=10, metavar="N",
                        help="每个平台返回条数,1-50,默认 10")
    args = parser.parse_args()
    if not 1 <= args.top <= 50:
        parser.error("--top 必须在 1-50 之间")
    return args


def collect(top: int = 20, only: str | None = None) -> dict:
    """进程内取数,返回与 CLI 输出完全一致的结构。

    给同目录的其他脚本(segment.py 等)直接 import 用,避免 subprocess + 临时文件。
    """
    start = time.monotonic()
    results, status = asyncio.run(fetch_all(only, top))
    elapsed_ms = int((time.monotonic() - start) * 1000)

    out: dict[str, list[dict]] = {}
    for platform, items in results.items():
        for rank, item in enumerate(items, 1):
            item["rank"] = rank
            item["url"] = url_for(platform, item["word"])
        out[platform] = items

    now = datetime.now(timezone(timedelta(hours=8)))
    return {
        "meta": {
            "fetched_at": now.isoformat(),
            "elapsed_ms": elapsed_ms,
            "platforms": status,
        },
        **out,
    }


def main() -> None:
    args = _parse_args()
    print(json.dumps(collect(args.top, args.platform), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
