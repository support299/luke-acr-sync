from django.urls import path

from . import views

app_name = "sync_app"

urlpatterns = [
    path("", views.custom_sync, name="custom_sync"),
]
