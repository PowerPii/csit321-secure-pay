import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit.models import AuditEvent, record

pytestmark = pytest.mark.django_db


def test_audit_rows_cannot_be_changed_through_the_model():
    event = record("payment.created", actor_type="system", target_id="pay_x")
    event.action = "edited"
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()
    with pytest.raises(PermissionError):
        AuditEvent.objects.all().update(action="edited")
    with pytest.raises(PermissionError):
        AuditEvent.objects.all().delete()


@pytest.mark.parametrize("sql", [
    "UPDATE audit_auditevent SET action = 'edited'",
    "DELETE FROM audit_auditevent",
])
def test_database_refuses_update_and_delete(sql):
    record("payment.created", actor_type="system", target_id="pay_x")
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql)
    assert AuditEvent.objects.get().action == "payment.created"
