from stock_research.quality import quality_status


def test_quality_status_ok():
    assert quality_status(metric=5200, min_value=5000) == "ok"


def test_quality_status_fail():
    assert quality_status(metric=10, min_value=5000) == "fail"
