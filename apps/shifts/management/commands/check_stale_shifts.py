import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.shifts.models import Shift
from apps.shifts.services import log_shift_action
from apps.shifts.notifications import trigger_shift_closing_notifications
from apps.settings_app.models import Settings

class Command(BaseCommand):
    help = 'Monitors open reception shifts and flags stale, overdue, or abandoned till sessions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=16,
            help='Threshold in hours after which an open shift is considered stale (default: 16)'
        )
        parser.add_argument(
            '--auto-force-close',
            action='store_true',
            help='Automatically force-close stale shifts using expected cash balance'
        )

    def handle(self, *args, **options):
        sett = Settings.get_settings()
        if getattr(sett, 'shift_operation_mode', None) == 'SINGLE_OPERATOR':
            self.stdout.write(self.style.NOTICE("Single-Operator / Owner-Managed Mode is active. Continuous rolling registers are not subject to stale shift alarms."))
            return

        threshold_hours = options['hours']
        auto_force_close = options['auto_force_close']
        now = timezone.now()
        cutoff_time = now - datetime.timedelta(hours=threshold_hours)

        stale_shifts = Shift.objects.filter(
            status__in=[Shift.Status.OPEN, Shift.Status.CLOSING],
            opened_at__lte=cutoff_time
        ).select_related('user')

        count = stale_shifts.count()
        self.stdout.write(self.style.NOTICE(f"Found {count} stale shift(s) open for > {threshold_hours} hours."))

        for shift in stale_shifts:
            hours_open = shift.duration_minutes // 60
            mins_open = shift.duration_minutes % 60
            duration_str = f"{hours_open}h {mins_open}m"

            if auto_force_close:
                shift.status = Shift.Status.FORCED_CLOSED
                shift.closed_at = now
                shift.closing_notes = f"[SYSTEM AUTO-CLOSE] Overdue shift open for {duration_str}"
                shift.actual_cash = shift.expected_cash
                shift.save()

                log_shift_action(
                    shift,
                    None,
                    'SYSTEM_AUTO_FORCE_CLOSE',
                    f"Shift #{shift.shift_number} was automatically force-closed after {duration_str}.",
                    {'duration_minutes': shift.duration_minutes}
                )
                trigger_shift_closing_notifications(shift)
                self.stdout.write(self.style.SUCCESS(f"Force-closed Shift #{shift.shift_number} ({shift.user.username}) - {duration_str}"))
            else:
                shift.status = Shift.Status.PENDING_REVIEW
                shift.save()

                log_shift_action(
                    shift,
                    None,
                    'STALE_SHIFT_FLAGGED',
                    f"Shift #{shift.shift_number} flagged as PENDING_REVIEW due to {duration_str} open session without closure.",
                    {'duration_minutes': shift.duration_minutes}
                )
                self.stdout.write(self.style.WARNING(f"Flagged Shift #{shift.shift_number} ({shift.user.username}) - {duration_str} as PENDING_REVIEW"))

        self.stdout.write(self.style.SUCCESS("Shift monitoring completed successfully."))
