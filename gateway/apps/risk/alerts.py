"""Fraud alerts (FR-FRD-08, UC-51; a Could requirement).

    raise_fraud_alert(event) -> FraudAlert | None

Called by checkout right after screening, inside the same transaction, so an alert exists
exactly when the flagged decision record does. Only Block and Verify decisions raise one.
Alerts reach analysts through the dashboard, which polls the unread count every few seconds
(NFR-PER-03: on the dashboard within 10 seconds); there is no email, to keep analysts'
inboxes for security alerts.
"""
from apps.risk.models import FraudAlert, ScreeningEvent, ScreeningOutcome

ALERT_OUTCOMES = (ScreeningOutcome.BLOCK, ScreeningOutcome.VERIFY)


def raise_fraud_alert(event: ScreeningEvent) -> FraudAlert | None:
    if event.outcome not in ALERT_OUTCOMES:
        return None
    alert, _ = FraudAlert.objects.get_or_create(screening=event)
    return alert
