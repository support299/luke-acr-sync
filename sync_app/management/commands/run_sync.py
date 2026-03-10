"""
Run the Drive -> ACR sync once in the current process (no Celery).
Use this to see exactly why no SyncedFile records were created: Drive list, download, ACR response.
"""
import traceback

from django.core.management.base import BaseCommand

from sync_app.tasks import run_sync_drive_to_acr


class Command(BaseCommand):
    help = "Run Drive -> ACR sync once in-process (no worker). Shows summary and any errors."

    def handle(self, *args, **options):
        self.stdout.write("Running sync (Drive -> download -> ACR -> record & cleanup)...")
        try:
            summary = run_sync_drive_to_acr()
            self.stdout.write("")
            self.stdout.write("Summary:")
            for key, value in summary.items():
                self.stdout.write(f"  {key}: {value}")
            if summary.get("last_acr_error"):
                self.stdout.write(self.style.WARNING(f"  Last ACR error: {summary['last_acr_error']}"))
            if summary.get("acr_success", 0) > 0:
                self.stdout.write(self.style.SUCCESS(f"  -> {summary['acr_success']} file(s) synced and recorded."))
            elif summary.get("acr_failed", 0) > 0:
                self.stdout.write(
                    self.style.ERROR(
                        f"  -> No records created: ACR upload failed for all {summary['acr_failed']} file(s). "
                        "Check last_acr_error and ACR credentials/endpoint."
                    )
                )
            elif summary.get("message") == "No new Drive files to sync.":
                self.stdout.write(
                    self.style.WARNING(
                        "  -> No new files in Drive folder (or all already in SyncedFile)."
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Exception: {e}"))
            traceback.print_exc()
