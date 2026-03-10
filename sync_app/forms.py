"""
Form for custom sync with date range and optional bucket ID.
"""
from django import forms
from django.core.exceptions import ValidationError


class CustomSyncForm(forms.Form):
    """From/to date range and optional ACR bucket ID for sync."""

    from_date = forms.DateField(
        required=True,
        label="From date",
        help_text="Only sync files modified on or after this date.",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}),
    )
    to_date = forms.DateField(
        required=False,
        label="To date",
        help_text="Only sync files modified on or before this date. Leave blank to use today.",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}),
    )
    bucket_id = forms.CharField(
        required=False,
        max_length=32,
        label="ACR Bucket ID",
        help_text="Default bucket is from .env (ACR_BUCKET_ID). Enter a bucket ID here only if you want to use a different bucket for this sync.",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Leave blank to use default from .env"}),
    )

    def clean(self):
        data = super().clean()
        from_date = data.get("from_date")
        to_date = data.get("to_date")
        if to_date is None:
            from django.utils import timezone
            data["to_date"] = timezone.localdate()
        else:
            data["to_date"] = to_date
        to_date = data["to_date"]
        if from_date and to_date and from_date > to_date:
            raise ValidationError("From date must be on or before To date.")
        bucket_id = (data.get("bucket_id") or "").strip()
        if bucket_id and not bucket_id.isdigit():
            raise ValidationError("Bucket ID must be a number.")
        return data
