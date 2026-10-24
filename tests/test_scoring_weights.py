from compliance_checker import SCORING_WEIGHTS


def test_indicator_weights_total_one_hundred():
    assert sum(SCORING_WEIGHTS.values()) == 100
