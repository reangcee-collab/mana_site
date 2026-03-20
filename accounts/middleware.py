"""
Multi-portal session middleware.

Allows staff, admin, and regular users to be logged in simultaneously
in the same browser (e.g. one Chrome window).

How it works:
  - /admin/* and /staff/* → session cookie: _staff_session
  - all other paths         → session cookie: sessionid

This way a customer can be logged in at /dashboard/ (sessionid)
while a staff member is logged in at /staff/ (_staff_session) at
the same time, without overwriting each other's session.
"""

import time
from importlib import import_module

from django.conf import settings
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


STAFF_SESSION_COOKIE = "_staff_session"
STAFF_PATH_PREFIXES = ("/admin/", "/staff/")


class MultiPortalSessionMiddleware:
    """
    Replace Django's built-in SessionMiddleware.
    Uses separate session cookies for the staff/admin portal vs the user portal.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        engine = import_module(settings.SESSION_ENGINE)
        self.SessionStore = engine.SessionStore

    def _cookie_name(self, request):
        path = getattr(request, "path_info", "/")
        if any(path.startswith(p) for p in STAFF_PATH_PREFIXES):
            return STAFF_SESSION_COOKIE
        return settings.SESSION_COOKIE_NAME

    def __call__(self, request):
        # --- process_request equivalent ---
        cookie_name = self._cookie_name(request)
        request._portal_cookie_name = cookie_name
        session_key = request.COOKIES.get(cookie_name)
        request.session = self.SessionStore(session_key)

        response = self.get_response(request)

        # --- process_response equivalent ---
        try:
            accessed = request.session.accessed
            modified = request.session.modified
            is_empty = request.session.is_empty()
        except AttributeError:
            return response

        if accessed:
            patch_vary_headers(response, ("Cookie",))

        if (modified or settings.SESSION_SAVE_EVERY_REQUEST) and not is_empty:
            if response.status_code != 500:
                if settings.SESSION_EXPIRE_AT_BROWSER_CLOSE:
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires = http_date(time.time() + max_age)
                request.session.save()
                response.set_cookie(
                    cookie_name,
                    request.session.session_key,
                    max_age=max_age,
                    expires=expires,
                    domain=settings.SESSION_COOKIE_DOMAIN,
                    path=settings.SESSION_COOKIE_PATH,
                    secure=settings.SESSION_COOKIE_SECURE or request.is_secure(),
                    httponly=settings.SESSION_COOKIE_HTTPONLY,
                    samesite=settings.SESSION_COOKIE_SAMESITE,
                )
        elif is_empty:
            # Delete cookie when session is empty (e.g. after logout)
            response.delete_cookie(
                cookie_name,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )

        return response
