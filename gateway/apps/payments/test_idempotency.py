"""Idempotency (API-CONTRACT.md section 5). Demo story S5 in docs/MVP-SCOPE.md."""
import threading
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.events.signing import verify
from apps.payments import views
from apps.payments.models import IdempotencyRecord, Payment
from conftest import valid_body

pytestmark = pytest.mark.django_db


def test_s5_duplicate_request(shop, error_schema):
    """S5: the merchant retries POST /v1/payments with the same Idempotency-Key.

    Same body returns the stored response and creates nothing; a different body gets 409.
    """
    retry_id = str(uuid.uuid4())  # a merchant uses a fresh UUID v4 per logical operation
    first = shop.create_payment(valid_body(), key=retry_id)
    assert first.status_code == 201

    retry = shop.create_payment(valid_body(), key=retry_id)
    assert retry.status_code == 201
    assert retry.content == first.content  # byte-identical stored body
    assert retry["Idempotent-Replayed"] == "true"
    assert verify(retry.content, retry["SecurePay-Signature"], shop.secret)
    assert retry["SecurePay-Request-Id"] != first["SecurePay-Request-Id"]
    assert Payment.objects.count() == 1

    different = shop.create_payment(valid_body(amount=9999), key=retry_id)
    assert different.status_code == 409
    error_schema.validate(different.json())
    assert different.json()["error"]["code"] == "idempotency_key_reused"
    assert verify(different.content, different["SecurePay-Signature"], shop.secret)
    assert Payment.objects.count() == 1

    # The 409 did not overwrite the stored reply.
    again = shop.create_payment(valid_body(), key=retry_id)
    assert again.content == first.content


def test_key_order_in_the_body_does_not_matter(shop):
    body = valid_body()
    first = shop.create_payment(body, key="order-key-01")
    reordered = dict(reversed(list(body.items())))
    assert shop.create_payment(reordered, key="order-key-01").content == first.content
    assert Payment.objects.count() == 1


def test_keys_are_scoped_to_the_merchant(shop, other_shop):
    a = shop.create_payment(key="shared-key-01")
    b = other_shop.create_payment(key="shared-key-01")
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_same_key_on_a_different_path_is_reused(shop):
    shop.create_payment(key="path-key-001")
    response = shop.post("/v1/payments?x=1", valid_body(), format="json",
                         headers={"Idempotency-Key": "path-key-001"})
    # The query string is not part of the path; same request, so it replays.
    assert response["Idempotent-Replayed"] == "true"


@pytest.mark.parametrize(("key", "code"), [
    (False, "idempotency_key_missing"),
    ("short", "idempotency_key_invalid"),
    ("has space in it", "idempotency_key_invalid"),
    ("x" * 256, "idempotency_key_invalid"),
])
def test_missing_or_bad_key_is_400_and_creates_nothing(shop, key, code):
    response = shop.create_payment(key=key)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert Payment.objects.count() == 0


def test_4xx_replies_are_stored_and_replayed(shop):
    first = shop.create_payment(valid_body(amount=10), key="small-amount-1")
    assert first.status_code == 400
    retry = shop.create_payment(valid_body(amount=10), key="small-amount-1")
    assert retry.status_code == 400
    assert retry.content == first.content
    assert retry["Idempotent-Replayed"] == "true"


def test_request_still_running_is_409_with_retry_after(shop):
    shop.create_payment(key="running-key-1")
    IdempotencyRecord.objects.update(status=IdempotencyRecord.Status.IN_PROGRESS,
                                     locked_at=timezone.now())
    response = shop.create_payment(key="running-key-1")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_request_in_progress"
    assert response["Retry-After"] == "1"


def test_a_crashed_request_is_taken_over_after_the_stale_timeout(shop):
    IdempotencyRecord.objects.create(
        merchant=shop.merchant, key="crashed-key-1", method="POST", path="/v1/payments",
        request_fingerprint=_fingerprint(valid_body()),
        locked_at=timezone.now() - timedelta(minutes=5),
        expires_at=timezone.now() + timedelta(hours=23),
    )
    response = shop.create_payment(key="crashed-key-1")
    assert response.status_code == 201
    assert Payment.objects.count() == 1


def test_a_5xx_is_not_stored_and_the_retry_runs_again(shop, monkeypatch):
    real = views.validate_create

    def boom(*args, **kwargs):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(views, "validate_create", boom)
    failed = shop.create_payment(key="flaky-key-001")
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "internal_error"
    assert not IdempotencyRecord.objects.exists()
    assert Payment.objects.count() == 0

    monkeypatch.setattr(views, "validate_create", real)
    retry = shop.create_payment(key="flaky-key-001")
    assert retry.status_code == 201
    assert "Idempotent-Replayed" not in retry


def test_keys_expire_after_24_hours(shop):
    first = shop.create_payment(key="old-key-0001")
    IdempotencyRecord.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    second = shop.create_payment(valid_body(amount=777), key="old-key-0001")
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert IdempotencyRecord.purge_expired() == 0  # the old record was replaced


def test_record_expires_24_hours_after_first_use(shop, settings):
    shop.create_payment(key="ttl-key-0001")
    record = IdempotencyRecord.objects.get()
    ttl = timedelta(hours=settings.GATEWAY_RULES["IDEMPOTENCY_TTL_HOURS"])
    assert record.expires_at - record.created_at == ttl


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicates_create_one_payment(make_merchant):
    """Two retries racing each other: exactly one payment, the other waits or replays."""
    shop = make_merchant()
    barrier = threading.Barrier(4)
    results = []

    def send():
        from conftest import MerchantClient

        client = MerchantClient(shop.merchant, shop.api_key, shop.key, shop.secret)
        barrier.wait()
        results.append(client.create_payment(key="race-key-0001"))
        connection.close()

    threads = [threading.Thread(target=send) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert Payment.objects.count() == 1
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) >= 1
    assert set(codes) <= {201, 409}
    for r in results:
        if r.status_code == 409:
            assert r.json()["error"]["code"] == "idempotency_request_in_progress"


def _fingerprint(body):
    from apps.payments.idempotency import request_fingerprint

    return request_fingerprint("POST", "/v1/payments", body)
