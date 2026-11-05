from apps.operations.test_cards import Behaviour, behaviour_for


def test_known_cards():
    assert behaviour_for("4242 4242 4242 4242") is Behaviour.APPROVE
    assert behaviour_for("4000000000000119") is Behaviour.TIMEOUT


def test_unknown_card_is_declined():
    assert behaviour_for("4111111111111111") is Behaviour.DECLINE_GENERIC
