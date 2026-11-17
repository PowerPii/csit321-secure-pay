"""Reset a staff member's two-step verification, for someone who lost both their phone and
their backup codes.

    python manage.py reset_staff_mfa ops@demoshop.sg

The authenticator device and every backup code are removed, so the next sign-in shows the
first-time setup QR code again (D2) and makes new backup codes. Run it only after checking
who is asking, outside the dashboard (for example in person). The reset is audited.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import BackupCode, StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit


class Command(BaseCommand):
    help = "Reset a staff member's authenticator app and backup codes (set up again at next sign-in)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        account = (StaffAccount.objects.select_related("user")
                   .filter(user__email__iexact=email.strip()).first())
        if account is None:
            raise CommandError(f"No staff account for {email}.")
        with transaction.atomic():
            devices, _ = TOTPDevice.objects.filter(user=account.user).delete()
            codes, _ = BackupCode.objects.filter(user=account.user).delete()
            StaffAccount.objects.filter(pk=account.pk).update(failed_attempts=0)
            audit("staff.mfa_reset", actor_type=AuditEvent.ActorType.SYSTEM,
                  actor_id="reset_staff_mfa", target_type="staff", target_id=account.public_id,
                  details={"devices_removed": devices, "backup_codes_removed": codes})
        self.stdout.write(self.style.SUCCESS(
            f"Two-step verification reset for {account.email}. The authenticator app is set "
            "up again at the next sign-in."))
