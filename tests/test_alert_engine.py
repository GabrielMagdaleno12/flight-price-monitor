from alert_engine import should_alert


def test_alerts_when_price_at_or_below_ceiling():
    assert should_alert(3000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=15) is True


def test_no_alert_when_price_above_ceiling_and_no_history():
    assert should_alert(4000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=15) is False


def test_alerts_on_drop_percentage_even_above_ceiling():
    # lowest ever seen was 4000; a 20% drop (3200) clears the 15% threshold (3400)
    assert should_alert(3200.0, price_ceiling=1000.0, lowest_price_seen=4000.0, drop_pct_threshold=15) is True


def test_no_alert_when_drop_below_threshold():
    # only a 5% drop from 4000 (3800), threshold requires 15%
    assert should_alert(3800.0, price_ceiling=1000.0, lowest_price_seen=4000.0, drop_pct_threshold=15) is False


def test_no_alert_when_no_ceiling_and_no_history():
    assert should_alert(3000.0, price_ceiling=None, lowest_price_seen=None, drop_pct_threshold=15) is False


def test_ceiling_alone_triggers_without_drop_threshold_configured():
    assert should_alert(3000.0, price_ceiling=3500.0, lowest_price_seen=None, drop_pct_threshold=None) is True
