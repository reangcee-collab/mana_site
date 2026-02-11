from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

def home(request):
    # user មិនទាន់ login -> ទៅ choose
    if not request.user.is_authenticated:
        return redirect("choose")
    # user login រួច -> ទៅ dashboard
    return redirect("/dashboard/")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("", include("accounts.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)