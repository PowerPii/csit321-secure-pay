import itertools

import pytest

from apps.payments.states import (
    FINAL_STATES,
    TRANSITIONS,
    InvalidTransition,
    check_transition,
)
from apps.payments.states import (
    PaymentStatus as S,
)


def test_every_state_has_a_transition_entry():
    assert set(TRANSITIONS) == set(S)


def test_happy_path_is_allowed():
    path = [S.CREATED, S.SCREENING, S.PROCESSING, S.AUTHORISED, S.CAPTURED]
    for a, b in itertools.pairwise(path):
        check_transition(a, b)


def test_unresolved_can_only_be_settled_by_reconciliation_outcomes():
    assert TRANSITIONS[S.UNRESOLVED] == {S.AUTHORISED, S.DECLINED}


@pytest.mark.parametrize("final", sorted(FINAL_STATES))
def test_final_states_cannot_move(final):
    for target in S:
        with pytest.raises(InvalidTransition):
            check_transition(final, target)


def test_cannot_void_a_captured_payment():  # requirements TL FR 5
    with pytest.raises(InvalidTransition):
        check_transition(S.CAPTURED, S.CANCELLED)
