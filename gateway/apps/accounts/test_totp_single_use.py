"""One authenticator code is accepted once per device and time step, across workers
(Codex release review, 18 Nov 2026). Before the fix each worker checked the code against
the device as it had loaded it, so two requests in flight could both accept one code."""
import threading

import pytest
from django.db import connections
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts import signin
from conftest import current_totp, make_staff_user


@pytest.mark.django_db(databases=["default", "vault"])
def test_a_code_is_used_up_even_by_a_request_holding_an_older_copy_of_the_device():
    account = make_staff_user("once@securepay.sg", "administrator")
    code = current_totp(account)
    first = TOTPDevice.objects.get(user=account.user, confirmed=True)
    second = TOTPDevice.objects.get(user=account.user, confirmed=True)  # another worker's copy
    assert signin.verify_totp(first, code)
    assert not signin.verify_totp(second, code)
    assert not signin.verify_totp(first, code)


@pytest.mark.django_db(databases=["default", "vault"])
def test_badly_formed_codes_are_refused_without_a_check():
    account = make_staff_user("shape@securepay.sg", "administrator")
    device = signin.confirmed_device(account)
    for code in (None, 123456, "", "12345", "1234567", "12a456"):
        assert not signin.verify_totp(device, code)
    assert not signin.verify_totp(None, current_totp(account))


@pytest.mark.django_db(transaction=True, databases=["default", "vault"])
def test_simultaneous_requests_with_one_code_succeed_once():
    account = make_staff_user("race@securepay.sg", "administrator")
    code = current_totp(account)
    copies = [TOTPDevice.objects.get(user=account.user, confirmed=True) for _ in range(6)]
    barrier = threading.Barrier(len(copies))
    results = []

    def attempt(device):
        try:
            barrier.wait()
            results.append(signin.verify_totp(device, code))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=attempt, args=(d,)) for d in copies]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False] * 5 + [True]
