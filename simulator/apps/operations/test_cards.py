"""Synthetic test cards: the card number decides what the simulated bank does.

Must match SIMULATOR-CONTRACT.md section 5. Never accept real card numbers. Anything not
listed here is declined as `card_declined`.
"""
from enum import StrEnum


class Behaviour(StrEnum):
    APPROVE = "approve"
    DECLINE_FUNDS = "decline_insufficient_funds"
    DECLINE_GENERIC = "decline_generic"
    TIMEOUT = "timeout"  # drop_response: record the approval, never reply (lost response, S4)
    SLOW = "slow"  # delay_response: record the approval, reply after the gateway gave up
    DROP_REQUEST = "drop_request"  # lost request: record nothing, never reply (no_record)


TEST_CARDS: dict[str, Behaviour] = {
    "4242424242424242": Behaviour.APPROVE,
    "5555555555554444": Behaviour.APPROVE,
    "4000000000009995": Behaviour.DECLINE_FUNDS,
    "4000000000000002": Behaviour.DECLINE_GENERIC,
    "4000000000000119": Behaviour.TIMEOUT,
    "4000000000000127": Behaviour.SLOW,
    "4000000000000135": Behaviour.DROP_REQUEST,
}


def digits_only(pan: str) -> str:
    return "".join(c for c in pan if c.isdigit())


def behaviour_for(pan: str) -> Behaviour:
    return TEST_CARDS.get(digits_only(pan), Behaviour.DECLINE_GENERIC)


def brand_for(pan: str) -> str:
    """Brand as the operation schema allows it: visa, mastercard or unknown."""
    digits = digits_only(pan)
    if digits.startswith("4"):
        return "visa"
    if digits[:2] in {"51", "52", "53", "54", "55"} or (
        len(digits) >= 4 and 2221 <= int(digits[:4]) <= 2720
    ):
        return "mastercard"
    return "unknown"


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0
