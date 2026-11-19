"""Samples behind the public status page (www.securepaysg.me/status).

The worker records one sample every five minutes (apps.status.service.record_sample): for
each part of the service, did it answer? The page shows today's state, 90 days of daily
uptime and the incidents those samples add up to. A gap in the samples means the worker
itself was not running.
"""
from django.db import models


class StatusSample(models.Model):
    taken_at = models.DateTimeField(db_index=True)
    # {"api": true, "database": true, "worker": true, "network": false, "shop": true}; a part
    # that was not checked (its probe URL not set) is left out.
    results = models.JSONField(default=dict)

    class Meta:
        ordering = ["taken_at"]

    def __str__(self):
        bad = [name for name, ok in self.results.items() if not ok]
        return f"{self.taken_at:%Y-%m-%d %H:%M} {'down: ' + ', '.join(bad) if bad else 'all up'}"
