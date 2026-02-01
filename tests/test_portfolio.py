from simulator.portfolio import Portfolio

def test_empty_portfolio_value():
    p = Portfolio.initial(cash=100.0)
    assert p.value({}) == 100.0
