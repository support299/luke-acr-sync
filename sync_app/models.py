"""
Models for sync_app.
SyncedFile is the source of truth so we don't process the same Google Drive file twice.
"""
from django.db import models


class SyncedFile(models.Model):
    """
    Tracks files that have been synced from Google Drive to ACR Cloud.
    drive_file_id is unique so we never process the same file twice.
    """

    # Google Drive file ID. Unique together with bucket_id so the same file
    # can be uploaded to more than one ACR bucket.
    drive_file_id = models.CharField(max_length=255, db_index=True)
    # ACR Console bucket this copy was uploaded to
    bucket_id = models.CharField(max_length=32, db_index=True, default="")
    # Original file name from Drive
    file_name = models.CharField(max_length=512)
    # When we successfully synced to ACR and created this record
    synced_at = models.DateTimeField(auto_now_add=True)
    # Status from ACR Cloud (e.g. "success", "pending", error code) for debugging
    acr_status = models.CharField(max_length=64, default="")
    # Duration in seconds from ACR (when available)
    acr_duration = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        ordering = ["-synced_at"]
        verbose_name = "Synced file"
        verbose_name_plural = "Synced files"
        constraints = [
            models.UniqueConstraint(
                fields=["drive_file_id", "bucket_id"],
                name="uniq_drive_file_bucket",
            ),
        ]

    def __str__(self):
        bucket = self.bucket_id or "?"
        return f"{self.file_name} ({self.drive_file_id}) -> {bucket}"
