"""
URL configuration for acr_sync project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from sync_app.views import login_view, logout_view, register_view

urlpatterns = [
    path("", RedirectView.as_view(url="/sync/", permanent=False)),
    path("admin/", admin.site.urls),
    path("accounts/login/", login_view, name="login"),
    path("accounts/register/", register_view, name="register"),
    path("accounts/logout/", logout_view, name="logout"),
    path("sync/", include("sync_app.urls")),
]
