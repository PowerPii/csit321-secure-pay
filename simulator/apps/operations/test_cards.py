"""Synthetic test cards: the card number decides what the simulated bank does.

Never accept real card numbers. Anything not listed here is declined.
"""
from enum import StrEnum


class Behaviour(StrEnum):
    APPROVE = "approve"
    DECLINE_FUNDS = "decline_insufficient_funds"
    DECLINE_GENERIC = "decline_generic"
    TIMEOUT = "timeout"  # accept the operation but drop the response (lost response, S4)
    SLOW = "slow"  # respond after a delay longer than the gateway's timeout


TEST_CARDS: dict[str, Behaviour] = {
    "4242424242424242": Behaviour.APPROVE,
    "5555555555554444": Behaviour.APPROVE,
    "4000000000009995": Behaviour.DECLINE_FUNDS,
    "4000000000000002": Behaviour.DECLINE_GENERIC,
    "4000000000000119": Behaviour.TIMEOUT,
    "4000000000000127": Behaviour.SLOW,
}


def behaviour_for(pan: str) -> Behaviour:
    return TEST_CARDS.get("".join(c for c in pan if c.isdigit()), Behaviour.DECLINE_GENERIC)
