"""
Views for sync_app: custom sync UI with date range and bucket ID.
"""
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import CustomSyncForm
from .tasks import run_sync_drive_to_acr


@require_http_methods(["GET", "POST"])
def custom_sync(request):
    """
    Custom sync page: form with from/to date and optional bucket ID.
    On POST, runs sync with date filter and optional bucket override, then redirects with result message.
    """
    if request.method == "GET":
        form = CustomSyncForm(initial={"to_date": timezone.localdate()})
        return render(request, "sync_app/custom_sync.html", {"form": form})

    form = CustomSyncForm(request.POST)
    if not form.is_valid():
        return render(request, "sync_app/custom_sync.html", {"form": form})

    from_date = form.cleaned_data["from_date"]
    to_date = form.cleaned_data["to_date"]
    # If user left to_date blank, form.clean() set it to today; inform them
    used_default_to_date = not (request.POST.get("to_date") or "").strip()
    bucket_id = (form.cleaned_data.get("bucket_id") or "").strip() or None

    try:
        summary = run_sync_drive_to_acr(
            from_date=from_date,
            to_date=to_date,
            bucket_id_override=bucket_id,
        )
    except Exception as e:
        messages.error(request, f"Sync failed: {e}")
        return render(request, "sync_app/custom_sync.html", {"form": form})

    if summary.get("error"):
        messages.error(request, summary["error"])
    else:
        if used_default_to_date:
            messages.info(request, "To date was not set; used today's date.")
        msg = summary.get("message", "Sync finished.")
        if summary.get("acr_success", 0) > 0:
            messages.success(
                request,
                f"{msg} {summary['acr_success']} file(s) synced successfully to ACR.",
            )
        elif summary.get("acr_failed", 0) > 0:
            messages.warning(
                request,
                f"{msg} {summary['acr_failed']} upload(s) failed. {summary.get('last_acr_error', '')}",
            )
        elif summary.get("message") == "No new Drive files to sync.":
            messages.info(request, "No new Drive files in the selected date range.")
        else:
            messages.success(request, msg)

    return redirect("sync_app:custom_sync")
