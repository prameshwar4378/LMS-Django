from django.core.management.base import BaseCommand
from apps.settings_app.activity_service import cleanup_old_history

class Command(BaseCommand):
    help = 'Deletes historical activity logs older than specified days (default 15 days).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=15,
            help='Retention period in days (default: 15)'
        )

    def handle(self, *args, **options):
        days = options['days']
        self.stdout.write(f"Pruning activity logs older than {days} days...")
        result = cleanup_old_history(days=days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {result['total_deleted']} historical records older than {days} days."
            )
        )
        for model_name, count in result['details'].items():
            self.stdout.write(f" - {model_name}: {count} records deleted")
