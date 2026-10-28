# -*- coding: utf-8 -*-
"""B站公开接口客户端。

封装视频信息、评论、字幕三类公开数据的获取与解析：
- 全部数据来自 B 站网页版公开 API，无需 API Key；
- 未登录可获取视频信息、评论与 CC 字幕；AI 生成字幕需要登录态（见 README 路线图）；
- 网络错误与 B 站业务错误统一抛出 :class:`BiliError`，由 MCP 工具层转成可读文本。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}

# BV 号固定为 BV + 10 位字母数字
_BV_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")


class BiliError(RuntimeError):
    """B站接口访问失败（网络错误、HTTP 错误或业务错误码）。"""


def extract_bvid(text: str) -> str:
    """从 BV 号或任意形式的视频链接中提取 BV 号。

    支持直接传 BV 号，也支持粘贴完整的分享链接，例如：
    - ``BV1GJ411x7h7``
    - ``https://www.bilibili.com/video/BV1GJ411x7h7/?p=1&share_source=xxx``
    """
    match = _BV_PATTERN.search(text or "")
    if not match:
        raise BiliError(
            f"无法从输入中解析 BV 号：{text!r}。"
            "请传入 BV 号或B站视频链接，例如 BV1GJ411x7h7"
        )
    return match.group(0)


def format_seconds(seconds: float) -> str:
    """把秒数格式化成 ``mm:ss`` 或 ``hh:mm:ss``。"""
    seconds = int(seconds)
    hour, rest = divmod(seconds, 3600)
    minute, second = divmod(rest, 60)
    if hour:
        return f"{hour:d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def subtitle_json_to_text(body: list[dict[str, Any]]) -> str:
    """把B站字幕 JSON（[{from, to, content}, ...]）转成带时间轴的纯文本。"""
    lines = []
    for item in body:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"[{format_seconds(item.get('from', 0))}] {content}")
    return "\n".join(lines)


class BiliClient:
    """异步 HTTP 客户端，对 B 站公开接口做薄封装。"""

    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            headers=HEADERS, timeout=timeout, follow_redirects=True
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET 并解析 JSON；B 站用 ``code: 0`` 表示成功，其余业务码转成异常。"""
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BiliError(f"B站接口 HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise BiliError(f"网络请求失败：{exc}") from exc

        payload = resp.json()
        if payload.get("code") != 0:
            raise BiliError(
                f"B站接口返回错误 code={payload.get('code')}：{payload.get('message', '未知错误')}"
            )
        return payload.get("data")

    async def get_video(self, bvid: str) -> dict[str, Any]:
        """获取视频元信息（标题、UP 主、时长、分区、各项数据）。"""
        data = await self._get_json(
            "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}
        )
        stat = data.get("stat", {})
        return {
            "bvid": data.get("bvid", bvid),
            "title": data.get("title", ""),
            "owner": data.get("owner", {}).get("name", ""),
            "duration_seconds": data.get("duration", 0),
            "pubdate": data.get("pubdate", 0),
            "desc": (data.get("desc") or "").strip(),
            "view": stat.get("view", 0),
            "like": stat.get("like", 0),
            "coin": stat.get("coin", 0),
            "favorite": stat.get("favorite", 0),
            "danmaku": stat.get("danmaku", 0),
            "reply": stat.get("reply", 0),
            "share": stat.get("share", 0),
        }

    async def get_subtitles(self, bvid: str) -> list[dict[str, Any]]:
        """获取视频的字幕轨道列表（未登录通常只有 UP 主上传的 CC 字幕）。"""
        video = await self._get_json(
            "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}
        )
        cid = video.get("cid")
        if not cid:
            raise BiliError("未拿到视频的 cid，无法查询字幕")
        player = await self._get_json(
            "https://api.bilibili.com/x/player/v2", params={"bvid": bvid, "cid": cid}
        )
        tracks = player.get("subtitle", {}).get("subtitles", [])
        return [
            {
                "language": track.get("lan", ""),
                "language_doc": track.get("lan_doc", ""),
                "url": ("https:" + track["subtitle_url"]) if track.get("subtitle_url", "").startswith("//") else track.get("subtitle_url", ""),
            }
            for track in tracks
        ]

    async def download_subtitle(self, url: str) -> str:
        """下载字幕文件（JSON）并转成带时间轴的纯文本。"""
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise BiliError(f"字幕下载失败：{exc}") from exc
        body = resp.json()
        # CC 字幕可能是 {body: [...]}，也可能直接就是数组
        items = body.get("body") if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise BiliError("字幕文件格式不符合预期（缺少 body 数组）")
        return subtitle_json_to_text(items)

    async def get_comments(
        self, bvid: str, page: int = 1, size: int = 20
    ) -> dict[str, Any]:
        """获取视频评论（默认按点赞排序），返回评论列表与总数。"""
        video = await self._get_json(
            "https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}
        )
        aid = video.get("aid")
        if not aid:
            raise BiliError("未拿到视频的 aid，无法查询评论")
        data = await self._get_json(
            "https://api.bilibili.com/x/v2/reply",
            params={"type": 1, "oid": aid, "pn": page, "ps": min(size, 49), "sort": 1},
        )
        comments = []
        for reply in data.get("replies") or []:
            comments.append(
                {
                    "user": reply.get("member", {}).get("uname", ""),
                    "like": reply.get("like", 0),
                    "content": (reply.get("content", {}).get("message") or "").strip(),
                    "reply_count": reply.get("rcount", 0),
                }
            )
        return {
            "total": data.get("page", {}).get("count", 0),
            "comments": comments,
        }
