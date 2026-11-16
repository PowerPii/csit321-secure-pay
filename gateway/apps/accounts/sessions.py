"""End a staff member's dashboard sessions (FR-ADM-02, UC-33).

Sessions are in the database (Django's default backend). Making the user inactive already
refuses their next request (apps.internal.access); deleting the session rows as well means
nothing is left to resume if the account is reinstated.
"""
from django.contrib.sessions.models import Session
from django.utils import timezone


def end_sessions(user) -> int:
    ended = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
            ended += 1
    return ended
