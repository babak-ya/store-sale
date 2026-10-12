from datetime import datetime, timezone
import pytest
from app.domain.stock import Stock
from app.domain.units import (DomainError, MAX_INT, integer, toman_to_rial, rial_to_toman,
    quantity, line_net, return_share, normalized_name)
from app.domain.clock import accounting_date, jalali_date


def test_persian_money_and_name():
    assert toman_to_rial("۱۰٫۱") == 101
    assert toman_to_rial("١٠.١") == 101
    assert rial_to_toman(101) == "10.1"
    assert normalized_name("  كالا ي  ") == "کالا ی"


@pytest.mark.parametrize("text", ["1.11", "1.00", "-1", "NaN", "Infinity", "1e3", "", "1,000", "9" * 33])
def test_bad_money(text):
    with pytest.raises(DomainError):
        toman_to_rial(text)


@pytest.mark.parametrize("value", [0.1, True, -1, MAX_INT + 1])
def test_bad_integer(value):
    with pytest.raises(DomainError):
        integer(value)


def test_quantity_precision_and_steps():
    assert quantity("۱", kind="weight", unit="g", step=1) == 1
    assert quantity("1.5", kind="weight", unit="kg", step=1) == 1500
    for text, kind, unit, step in [("0.0001", "weight", "g", 1), ("1.5", "count", "count", 1),
                                  ("0", "count", "count", 1), ("126", "weight", "g", 125), ("1000", "weight", "mg", 1),
                                  ("0.125", "weight", "g", 1), ("0.0005", "weight", "kg", 1)]:
        with pytest.raises(DomainError):
            quantity(text, kind=kind, unit=unit, step=step)


def test_saffron_acceptance():
    stock = Stock().receive(8, 800000)
    stock, cost = stock.issue(1)
    net = line_net(150000, 1, 1)
    assert (net, cost, net - cost, stock.qty, stock.value) == (150000, 100000, 50000, 7, 700000)


def test_rounding_and_complete_depletion():
    s = Stock(3, 100)
    costs = []
    for _ in range(3):
        s, cost = s.issue(1)
        costs.append(cost)
    assert costs == [33, 34, 33]
    assert s == Stock()
    returned = 0
    increments = []
    for q in range(1, 4):
        value = return_share(100, 3, q, returned)
        increments.append(value)
        returned += value
    assert increments == [33, 34, 33]
    assert returned == 100


def test_continuous_plan_stock_and_profit():
    # Stock/cost part of the plan only. AR/AP and payments are not implemented yet.
    s = Stock().receive(1000, 100000).receive(500, 70000)
    s, c1 = s.issue(600)
    assert (s, c1) == (Stock(900, 102000), 68000)
    s = s.receive(500, 65000)
    s, c2 = s.issue(700)
    assert c2 == 83500
    r1 = return_share(c1, 600, 100, 0)
    s = s.receive(100, r1)
    assert s == Stock(800, 94833)
    s, c3 = s.issue(300)
    assert (s, c3) == (Stock(500, 59271), 35562)
    r2 = return_share(c2, 700, 200, 0)
    s = s.receive(200, r2)
    r3 = return_share(c1, 600, 200, r1)
    s = s.receive(100, r3)
    assert (r1, r2, r3) == (11333, 23857, 11334)
    assert s == Stock(800, 94462)
    net_sales = 90000 + 112000 + 51000 - 15000 - 32000 - 15000
    net_cogs = c1 + c2 + c3 - r1 - r2 - r3
    assert (net_sales, net_cogs, net_sales - net_cogs) == (191000, 140538, 50462)


def test_purchase_return_valuation():
    s = Stock().receive(1, 100).receive(1, 200)
    s, cost = s.issue(1)
    assert (s, cost, 100 - cost) == (Stock(1, 150), 150, -50)


def test_invalid_stock_discount_return_overflow():
    for call in [lambda: Stock(0, 1), lambda: Stock(1, 1).issue(2),
                 lambda: line_net(10, 1, 1, 11), lambda: line_net(MAX_INT, 2, 1),
                 lambda: return_share(100, 1, 2, 0), lambda: Stock(MAX_INT, 1).receive(1, 1)]:
        with pytest.raises(DomainError):
            call()


def test_tehran_midnight_and_jalali_leap_boundary():
    before = datetime(2025, 3, 20, 20, 29, 59, tzinfo=timezone.utc)
    after = datetime(2025, 3, 20, 20, 30, tzinfo=timezone.utc)
    assert accounting_date(before) == "2025-03-20"
    assert accounting_date(after) == "2025-03-21"
    assert jalali_date(before) == "1403/12/30"
    assert jalali_date(after) == "1404/01/01"
    with pytest.raises(ValueError):
        accounting_date(datetime(2025, 1, 1))


def test_exact_kg_boundaries_and_display():
    from app.domain.units import display_weight
    assert quantity('0.001', kind='weight', unit='kg', step=1) == 1
    assert quantity('۰٫۲۵۰', kind='weight', unit='kg', step=1) == 250
    assert quantity('١٫٥', kind='weight', unit='kg', step=1) == 1500
    assert quantity(str(MAX_INT), kind='weight', unit='g', step=1) == MAX_INT
    assert display_weight(1, 'kg') == '0.001'
    assert display_weight(0, 'kg') == '0.000'
    assert display_weight(MAX_INT, 'kg') == '9223372036854775.807'
    for text in ['0.0001', '0.2501', '0', '-1', str(MAX_INT)]:
        with pytest.raises(DomainError):
            quantity(text, kind='weight', unit='kg', step=1)
    # Price per kg and price per gram represent the same exact money calculation.
    assert line_net(1200000, 250, 1000) == line_net(1200, 250, 1) == 300000
