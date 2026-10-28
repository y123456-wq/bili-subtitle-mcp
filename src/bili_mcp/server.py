# -*- coding: utf-8 -*-
"""MCP 工具层：把 B 站客户端能力暴露成 AI 客户端可调用的工具。

工具的 docstring 会直接成为大模型看到的工具说明，因此写清楚
「什么时候该用这个工具、参数是什么」，能显著提升工具调用的准确率。
"""

from __future__ import annotations

import functools
import time

from mcp.server.fastmcp import FastMCP

from .bilibili import BiliClient, BiliError, extract_bvid, format_seconds

mcp = FastMCP(
    "bili-video",
    instructions=(
        "获取B站视频的元信息、热门评论和字幕。"
        "video 参数既支持 BV 号（如 BV1GJ411x7h7），也支持完整的视频链接。"
    ),
)

_client: BiliClient | None = None


def _get_client() -> BiliClient:
    """惰性创建进程级共享客户端（复用连接池）。"""
    global _client
    if _client is None:
        _client = BiliClient()
    return _client


def _safe_call(fn):
    """把底层异常转成给模型看的可读文本，避免客户端直接崩掉。"""

    @functools.wraps(fn)  # 保留原函数名/docstring，FastMCP 依赖它们注册工具
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except BiliError as exc:
            return f"查询失败：{exc}"

    return wrapper


@mcp.tool()
@_safe_call
async def get_video_info(video: str) -> str:
    """获取B站视频的元信息：标题、UP主、时长、发布时间、播放/点赞/投币等数据、简介。

    想了解“这是个什么视频、火不火”时先调用这个工具。
    Args:
        video: BV 号或B站视频链接，例如 BV1GJ411x7h7
    """
    bvid = extract_bvid(video)
    info = await _get_client().get_video(bvid)
    return "\n".join(
        [
            f"标题：{info['title']}",
            f"UP主：{info['owner']}",
            f"时长：{format_seconds(info['duration_seconds'])}",
            f"发布时间：{time.strftime('%Y-%m-%d', time.localtime(info['pubdate']))}",
            (
                f"数据：播放 {info['view']} | 点赞 {info['like']} | 投币 {info['coin']} | "
                f"收藏 {info['favorite']} | 弹幕 {info['danmaku']} | 评论 {info['reply']}"
            ),
            f"简介：{info['desc'][:200] or '（无）'}",
        ]
    )


@mcp.tool()
@_safe_call
async def get_video_comments(video: str, count: int = 10, page: int = 1) -> str:
    """获取B站视频的热门评论（按点赞排序），用于了解观众评价和舆论风向。

    Args:
        video: BV 号或B站视频链接
        count: 返回评论条数（1-49，默认 10）
        page: 评论页码，从 1 开始
    """
    bvid = extract_bvid(video)
    count = max(1, min(int(count), 49))
    result = await _get_client().get_comments(bvid, page=page, size=count)
    if not result["comments"]:
        return "该视频没有获取到评论（可能评论已关闭或视频太新）。"
    lines = [f"共 {result['total']} 条评论，当前第 {page} 页热评：", ""]
    for i, c in enumerate(result["comments"], 1):
        content = c["content"][:150] + ("…" if len(c["content"]) > 150 else "")
        lines.append(f"{i}. [赞 {c['like']}] {c['user']}：{content}")
    return "\n".join(lines)


@mcp.tool()
@_safe_call
async def list_video_subtitles(video: str) -> str:
    """列出B站视频可用的字幕轨道（语言与链接信息）。

    先用这个工具确认视频有没有字幕，再用 get_subtitle_text 获取字幕正文。
    注意：未登录只能看到 UP 主上传的 CC 字幕，B 站 AI 字幕需要登录态，本服务器暂不支持。
    Args:
        video: BV 号或B站视频链接
    """
    bvid = extract_bvid(video)
    tracks = await _get_client().get_subtitles(bvid)
    if not tracks:
        return (
            "该视频没有可获取的字幕轨道。"
            "未登录状态下只能获取 UP 主手动上传的 CC 字幕；"
            "B站 AI 生成字幕需要登录 Cookie，暂不支持。"
        )
    return "\n".join(
        f"- {t['language_doc']}（{t['language']}）" + ("　[可下载]" if t["url"] else "")
        for t in tracks
    )


@mcp.tool()
@_safe_call
async def get_subtitle_text(video: str, language: str = "") -> str:
    """获取B站视频的字幕正文（带 [分:秒] 时间轴的纯文本），适合用来总结视频内容。

    建议先用 list_video_subtitles 确认存在字幕轨道。
    Args:
        video: BV 号或B站视频链接
        language: 字幕语言代码，如 zh-Hans；留空自动取第一个可用轨道
    """
    bvid = extract_bvid(video)
    client = _get_client()
    tracks = await client.get_subtitles(bvid)
    if not tracks:
        return (
            "该视频没有可获取的字幕轨道。"
            "未登录状态下只能获取 UP 主手动上传的 CC 字幕。"
        )
    track = tracks[0]
    if language:
        for t in tracks:
            if t["language"] == language:
                track = t
                break
        else:
            available = "、".join(t["language"] for t in tracks)
            return f"没有找到语言为 {language} 的字幕，可用语言：{available}"
    if not track["url"]:
        return "该字幕轨道没有可下载的文件。"
    return await client.download_subtitle(track["url"])


def run() -> None:
    """以 stdio 方式启动 MCP 服务器（供 Claude Desktop / Cursor 等客户端拉起）。"""
    mcp.run()
