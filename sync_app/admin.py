from django.contrib import admin
from .models import SyncedFile


@admin.register(SyncedFile)
class SyncedFileAdmin(admin.ModelAdmin):
    list_display = ("file_name", "drive_file_id", "acr_duration", "acr_status", "synced_at")
    search_fields = ("file_name", "drive_file_id")
    readonly_fields = ("synced_at",)
