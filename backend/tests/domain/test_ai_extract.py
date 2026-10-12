"""AI 提取领域规则：提示词与响应解析（纯函数）。"""

from __future__ import annotations

from app.domain.ai_extract import build_extract_messages, parse_extract_response


class Test响应解析:
    def test_标准JSON数组(self):
        rows = parse_extract_response(
            '[{"name":"John Smith","title":"Sales Manager","email":"john@x.com","phone":null}]'
        )
        assert len(rows) == 1
        assert rows[0].name == "John Smith"
        assert rows[0].title == "Sales Manager"
        assert rows[0].email == "john@x.com"

    def test_代码块围栏剥离(self):
        rows = parse_extract_response(
            '```json\n[{"name":null,"title":"","email":"info@x.com"}]\n```'
        )
        assert rows and rows[0].name is None and rows[0].email == "info@x.com"

    def test_非法JSON返回空(self):
        assert parse_extract_response("抱歉我无法…") == []

    def test_无邮箱行丢弃与去重(self):
        rows = parse_extract_response(
            '[{"name":"A","email":"a@x.com"},{"name":"B","email":""},'
            '{"name":"C","email":"a@x.com"}]'
        )
        assert len(rows) == 1

    def test_null字符串姓名归None(self):
        rows = parse_extract_response('[{"name":"null","email":"g@x.com"}]')
        assert rows[0].name is None


class Test提示词:
    def test_带URL与截断文本(self):
        messages = build_extract_messages("x" * 20000, "https://a.com/contact")
        assert messages[0]["role"] == "system"
        assert "https://a.com/contact" in messages[1]["content"]
        assert len(messages[1]["content"]) < 14000  # 12k 截断生效
