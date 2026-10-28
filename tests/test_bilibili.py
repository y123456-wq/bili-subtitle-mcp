# -*- coding: utf-8 -*-
"""单元测试：覆盖链接解析、时间格式化和字幕文本转换（不发起网络请求）。"""

import unittest

from bili_mcp.bilibili import (
    BiliError,
    extract_bvid,
    format_seconds,
    subtitle_json_to_text,
)


class ExtractBvidTest(unittest.TestCase):
    def test_plain_bvid(self):
        self.assertEqual(extract_bvid("BV1GJ411x7h7"), "BV1GJ411x7h7")

    def test_full_url_with_params(self):
        url = "https://www.bilibili.com/video/BV1GJ411x7h7/?p=1&share_source=weixin"
        self.assertEqual(extract_bvid(url), "BV1GJ411x7h7")

    def test_short_share_text(self):
        text = "看看这个 https://b23.tv/BV1GJ411x7h7 超有意思"
        self.assertEqual(extract_bvid(text), "BV1GJ411x7h7")

    def test_invalid_input_raises(self):
        with self.assertRaises(BiliError):
            extract_bvid("https://www.bilibili.com/video/av170001")

    def test_empty_input_raises(self):
        with self.assertRaises(BiliError):
            extract_bvid("")


class FormatSecondsTest(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(format_seconds(65), "01:05")

    def test_hours(self):
        self.assertEqual(format_seconds(3671), "1:01:11")

    def test_zero(self):
        self.assertEqual(format_seconds(0), "00:00")


class SubtitleJsonToTextTest(unittest.TestCase):
    def test_basic_conversion(self):
        body = [
            {"from": 0.0, "to": 1.2, "content": "大家好"},
            {"from": 61.5, "to": 63.0, "content": "今天聊聊 MCP"},
            {"from": 62.0, "to": 64.0, "content": "  "},  # 空白内容应被跳过
        ]
        text = subtitle_json_to_text(body)
        self.assertEqual(text.splitlines()[0], "[00:00] 大家好")
        self.assertEqual(text.splitlines()[1], "[01:01] 今天聊聊 MCP")
        self.assertEqual(len(text.splitlines()), 2)

    def test_empty_body(self):
        self.assertEqual(subtitle_json_to_text([]), "")


if __name__ == "__main__":
    unittest.main()
