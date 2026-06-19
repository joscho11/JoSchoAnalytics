"""Hermetic tests for the Kelly staking math — no network/data."""
import kelly_staking as ks


def test_american_to_decimal():
    assert abs(ks.american_to_decimal(-110) - 1.9091) < 1e-3
    assert abs(ks.american_to_decimal(+150) - 2.5) < 1e-9
    assert abs(ks.american_to_decimal(-200) - 1.5) < 1e-9


def test_kelly_fraction():
    # at -110 (b=0.909), break-even p = 0.524 -> Kelly 0; edge -> positive, no-edge -> 0
    dec = ks.american_to_decimal(-110)
    assert ks.kelly_fraction(0.524, dec) < 1e-3          # ~break-even
    assert ks.kelly_fraction(0.50, dec) == 0.0           # below break-even floored at 0
    assert 0.10 < ks.kelly_fraction(0.61, dec) < 0.20    # real edge -> ~0.18 full Kelly


def test_wilson_lower_below_point_estimate():
    lo = ks.wilson_lower(450, 738)        # ~61% over 738
    assert 0.55 < lo < 0.61               # lower than the 61% point estimate
    assert ks.wilson_lower(0, 0) == 0.0


def test_wilson_tighter_with_more_data():
    # same rate, bigger n -> lower bound closer to the point estimate
    assert ks.wilson_lower(610, 1000) > ks.wilson_lower(61, 100)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
