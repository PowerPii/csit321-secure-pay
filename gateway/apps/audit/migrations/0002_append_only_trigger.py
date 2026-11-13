"""Refuse UPDATE and DELETE on audit rows at the database level (NFR-AUD).

The model already refuses it; this also covers raw SQL and anyone with database access
through the gateway role. TRUNCATE is not covered, so test databases can still be reset.
"""
from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_auditevent_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit events are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditevent_append_only
    BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_auditevent_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_auditevent_append_only ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_auditevent_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
