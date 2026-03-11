"""
Views for sync_app: custom sync UI with date range and bucket ID.
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from datetime import timedelta

from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import CustomSyncForm
from .models import SyncedFile
from .tasks import run_sync_drive_to_acr


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Function-based login view to avoid 405 issues."""
    if request.user.is_authenticated:
        return redirect("sync_app:custom_sync")
    if request.method == "GET":
        return render(request, "sync_app/login.html", {"form": None, "next": request.GET.get("next", "")})
    from django.contrib.auth.forms import AuthenticationForm
    form = AuthenticationForm(request, data=request.POST)
    if form.is_valid():
        user = form.get_user()
        login(request, user)
        next_url = request.POST.get("next", "").strip()
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect("sync_app:custom_sync")
    return render(request, "sync_app/login.html", {"form": form, "next": request.POST.get("next", "")})


@require_http_methods(["GET", "POST"])
def register_view(request):
    """User registration view."""
    if request.user.is_authenticated:
        return redirect("sync_app:custom_sync")
    if request.method == "GET":
        form = UserCreationForm()
        return render(request, "sync_app/register.html", {"form": form})
    form = UserCreationForm(request.POST)
    if form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully. Welcome!")
        return redirect("sync_app:custom_sync")
    return render(request, "sync_app/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Logout view that accepts GET (for link clicks) and POST."""
    logout(request)
    return redirect("login")


@login_required
@require_http_methods(["GET", "POST"])
def custom_sync(request):
    """
    Custom sync page: form with from/to date and optional bucket ID.
    On POST, runs sync with date filter and optional bucket override, then redirects with result message.
    """
    if request.method == "GET":
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        form = CustomSyncForm(initial={"from_date": yesterday, "to_date": today})
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


def _format_duration(secs_str):
    """Format duration string (e.g. '312.485') as '5m 12s' or '45s'."""
    if not secs_str:
        return None
    try:
        total = float(secs_str)
        mins = int(total // 60)
        secs = total % 60
        if mins > 0:
            return f"{mins}m {secs:.1f}s"
        return f"{secs:.1f}s"
    except (ValueError, TypeError):
        return secs_str


@login_required
def synced_files_list(request):
    """Display all synced files with file name, duration, synced date/time, etc."""
    files = SyncedFile.objects.all().order_by("-synced_at")
    for f in files:
        f.duration_display = _format_duration(f.acr_duration)
    return render(request, "sync_app/synced_files.html", {"files": files})
