from decimal import Decimal

from app.services import auto_trade as auto_trade_service


def test_rule_target_price_is_calculated_from_entry_price():
    entry_price = Decimal("100")

    assert auto_trade_service.calculate_rule_target_price(entry_price, "stop_loss", Decimal("5")) == Decimal("95")
    assert auto_trade_service.calculate_rule_target_price(entry_price, "take_profit", Decimal("10")) == Decimal("110")
