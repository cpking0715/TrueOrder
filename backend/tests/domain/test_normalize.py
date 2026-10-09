"""归一化规则：公司名、国家、地址城市、同名冲突、税号有效性。"""

import pytest

from app.domain.normalize import (
    guess_city,
    hs_family_prefix,
    is_valid_hs,
    name_conflict,
    normalize_company_name,
    normalize_country,
)


class Test公司名归一化:
    def test_去标点_大写_合并空白(self):
        assert normalize_company_name("brooklyn   apparel, llc.") == normalize_company_name(
            "BROOKLYN APPAREL LLC"
        )

    def test_剥离常见法律后缀(self):
        # INC / LLC / CO LTD / GMBH 等后缀不参与同名识别
        assert normalize_company_name("ACME INC") == normalize_company_name("ACME CORPORATION")
        assert normalize_company_name("ACME CORP") == "ACME"
        assert normalize_company_name("ACME CO LTD") == "ACME"

    def test_后缀剥离至少保留一个词(self):
        assert normalize_company_name("LLC") != ""

    def test_连续后缀逐层剥离(self):
        assert normalize_company_name("ACME COMPANY LIMITED") == "ACME"

    def test_空输入返回空串(self):
        assert normalize_company_name("") == ""
        assert normalize_company_name("   ") == ""


class Test国家归一化:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("US", "US"),
            ("USA", "US"),
            ("U.S.A.", "US"),
            ("UNITED STATES", "US"),
            ("CHINA", "CN"),
            ("P R CHINA", "CN"),
            ("PEOPLES REPUBLIC OF CHINA", "CN"),
            ("VIETNAM", "VN"),
            ("VIET NAM", "VN"),
            ("HONG KONG", "HK"),
            ("MEXICO", "MX"),
        ],
    )
    def test_常见写法映射(self, raw, expected):
        assert normalize_country(raw) == expected

    def test_未知长写法返回大写原文(self):
        assert normalize_country("Wakanda") == "WAKANDA"

    def test_两位字母直接通过(self):
        assert normalize_country("de") == "DE"


class Test地址城市猜测与同名冲突:
    def test_美式地址取城市段(self):
        assert guess_city("350 FIFTH AVE, NEW YORK NY 10118, USA") == "NEW YORK"
        assert guess_city("1600 AMPHITHEATRE PKWY, MOUNTAIN VIEW CA 94043") == "MOUNTAIN VIEW"

    def test_找不到城市模式时取第一个纯字母段(self):
        city = guess_city("NO 88 JALAN Industri, Shah Alam")
        assert city in {"NO JALAN INDUSTRI", "SHAH ALAM"}

    def test_空地址返回空(self):
        assert guess_city("") == ""

    def test_同名不同城市判为冲突(self):
        assert name_conflict(
            [("ACME LLC", "1 A ST, NEW YORK NY 10001"), ("ACME INC", "2 B ST, AUSTIN TX 78701")]
        )

    def test_同名同城市不算冲突(self):
        assert not name_conflict(
            [("ACME LLC", "1 A ST, NEW YORK NY 10001"), ("ACME INC", "9 C AVE, NEW YORK NY 10002")]
        )

    def test_无地址信息不算冲突(self):
        assert not name_conflict([("ACME", ""), ("ACME LLC", "")])


class Test税号有效性:
    @pytest.mark.parametrize(
        "code",
        ["620462", "480810", "6204620000", "62046200"],
    )
    def test_合法税号(self, code):
        assert is_valid_hs(code)

    @pytest.mark.parametrize(
        "code",
        ["", "6204", "62046", "6204X2", "62 0462", "000000", "999999999999", "N/A", "6204620O"],
    )
    def test_非法或明显误码(self, code):
        assert not is_valid_hs(code)

    def test_取税号族前缀(self):
        assert hs_family_prefix("6204620000") == "6204"
        assert hs_family_prefix("620462") == "6204"
