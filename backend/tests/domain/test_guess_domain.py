"""域名猜测纯函数测试。"""

from __future__ import annotations

from app.domain.guess_domain import guess_domains


class Test域名猜测:
    def test_全词连写优先(self):
        domains = guess_domains("Karen Kane, Inc.")
        assert domains[0] == "karenkane.com"

    def test_法律后缀剥离(self):
        assert guess_domains("Liverpool Jeans Company, LLC")[0] == "liverpooljeans.com"

    def test_多词取首末(self):
        domains = guess_domains("John Paul Richard Inc")
        assert domains[0] == "johnpaulrichard.com"

    def test_首字母缩写模式(self):
        domains = guess_domains("Pacific Fashion Wholesale")
        # 全词太长 → 首字母+末词：pfashion.com 或类似
        assert any("fashion" in d for d in domains)

    def test_停用词全剥后退化(self):
        domains = guess_domains("The Group")
        assert domains  # 不返回空

    def test_空名返回空(self):
        assert guess_domains("") == []
        assert guess_domains("LLC") == []

    def test_截断过长域名(self):
        domains = guess_domains("International Manufacturing Corporation of America")
        assert all(len(d.split(".")[0]) <= 30 for d in domains)

    def test_去重(self):
        domains = guess_domains("Acme Inc")
        assert len(domains) == len(set(domains))
