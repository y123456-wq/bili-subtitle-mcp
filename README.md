# bili-subtitle-mcp

一个 [MCP（Model Context Protocol）](https://modelcontextprotocol.io) 服务器，让 Claude Desktop、Cursor 等 AI 客户端可以直接"看"B站视频：获取视频信息、热门评论和字幕。

**无需任何 API Key**，全部数据来自 B 站网页版公开接口。

## 功能

| 工具 | 说明 |
|------|------|
| `get_video_info` | 视频元信息：标题、UP主、时长、播放/点赞/投币等数据、简介 |
| `get_video_comments` | 热门评论（按点赞排序，支持分页） |
| `list_video_subtitles` | 列出视频可用的字幕轨道 |
| `get_subtitle_text` | 获取字幕正文（带 `[分:秒]` 时间轴的纯文本，适合总结视频内容） |

## 快速开始

```bash
pip install .
```

在 MCP 客户端中注册（以 Claude Desktop 为例，`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "bili-video": {
      "command": "bili-subtitle-mcp"
    }
  }
}
```

之后就可以直接对 AI 说：

> 帮我看看这个视频讲了什么：https://www.bilibili.com/video/BV1GJ411x7h7

AI 会自动调用工具获取视频信息和字幕，再给你总结。

## 已知限制

- **字幕**：未登录状态下只能获取 UP 主手动上传的 CC 字幕。B 站 AI 生成字幕需要登录态，暂不支持（见路线图）。
- **弹幕**：B 站弹幕接口已迁移到 protobuf 协议，暂未支持（见路线图）。
- **频率限制**：本服务器对 B 站接口只做只读访问且自带间隔，请勿高频滥用；数据版权归 B 站与 UP 主所有，仅供个人学习研究。

## 路线图

- [ ] 支持 `SESSDATA` 环境变量（可选），解锁 AI 字幕
- [ ] 弹幕获取（protobuf 协议解析），支持按时间轴分析高能片段
- [ ] 分 P 视频（多 cid）支持
- [ ] 视频合集 / 收藏夹批量分析

## 开发

```bash
pip install .
python -m unittest discover -s tests -v
```

> 注意：editable 安装（`pip install -e .`）在含中文/非 ASCII 的路径下有已知问题，请使用上面的普通安装方式。

项目结构：

```
src/bili_mcp/
├── bilibili.py   # B站公开接口客户端（BV号解析、视频信息、评论、字幕）
├── server.py     # MCP 工具层（4 个工具的定义与文本格式化）
└── __main__.py   # 命令行入口
tests/            # 单元测试（不依赖网络）
```

## License

[MIT](LICENSE)
