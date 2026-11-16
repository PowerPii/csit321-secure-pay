"""Refuse UPDATE and DELETE on audit seals too (NFR-INT-02), like the entries (0002)."""
from django.db import migrations

FORWARD = """
CREATE TRIGGER audit_auditseal_append_only
    BEFORE UPDATE OR DELETE ON audit_auditseal
    FOR EACH ROW EXECUTE FUNCTION audit_auditevent_append_only();
"""

REVERSE = "DROP TRIGGER IF EXISTS audit_auditseal_append_only ON audit_auditseal;"


class Migration(migrations.Migration):
    dependencies = [("audit", "0003_audit_chain_and_correlation")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
