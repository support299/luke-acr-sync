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

    # Google Drive file ID (unique per file in the folder)
    drive_file_id = models.CharField(max_length=255, unique=True, db_index=True)
    # Original file name from Drive
    file_name = models.CharField(max_length=512)
    # When we successfully synced to ACR and created this record
    synced_at = models.DateTimeField(auto_now_add=True)
    # Status from ACR Cloud (e.g. "success", "pending", error code) for debugging
    acr_status = models.CharField(max_length=64, default="")

    class Meta:
        ordering = ["-synced_at"]
        verbose_name = "Synced file"
        verbose_name_plural = "Synced files"

    def __str__(self):
        return f"{self.file_name} ({self.drive_file_id})"
