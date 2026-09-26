from polymarket_monitor import extract_line, classify_market, parse_jsonish


def test_extract_line():
    assert extract_line("Team A Spread -4.5") == -4.5
    assert extract_line("Over 167.5") == 167.5
    assert extract_line("nothing") is None


def test_parse_jsonish():
    assert parse_jsonish('["a", "b"]') == ["a", "b"]


def test_classify_market():
    assert classify_market({"sports": {"sportsMarketType": "spreads"}}) == "spread"
    assert classify_market({"sports": {"sportsMarketType": "totals"}}) == "total"


if __name__ == "__main__":
    test_extract_line(); test_parse_jsonish(); test_classify_market()
    print("3 tests passed")
