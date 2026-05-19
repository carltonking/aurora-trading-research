from aurora.risk.models import (
    RISK_APPROVED,
    RiskDecision,
    TradeCandidate,
    risk_decision_to_dict,
)


def test_risk_decision_to_dict_returns_expected_keys() -> None:
    candidate = TradeCandidate(symbol="AAPL", side="buy", quantity=10, price=100)
    decision = RiskDecision(
        status=RISK_APPROVED,
        approved=True,
        original_quantity=10,
        final_quantity=10,
        reasons=["approved"],
        candidate=candidate,
    )

    result = risk_decision_to_dict(decision)

    assert result["status"] == RISK_APPROVED
    assert result["approved"] is True
    assert result["candidate"]["symbol"] == "AAPL"
    assert set(result) == {
        "status",
        "approved",
        "original_quantity",
        "final_quantity",
        "reasons",
        "candidate",
    }
