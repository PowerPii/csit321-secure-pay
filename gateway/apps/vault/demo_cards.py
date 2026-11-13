"""Synthetic gateway-side test cards (never real numbers), kept in the vault module so card
numbers stay inside apps/vault (CONTRIBUTING rule 1).

The simulator's own test cards decide what the bank does (SIMULATOR-CONTRACT.md section 5).
These decide what the gateway's screening does before the simulator is ever called.
"""
from apps.vault.fingerprint import card_fingerprint

DEMO_CARDS = {
    # On the seeded block list: screening blocks it (demo story S3).
    "blocklisted": "4000000000000101",
}


def demo_card_fingerprint(name: str) -> str:
    return card_fingerprint(DEMO_CARDS[name])
