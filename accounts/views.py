from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from .models import User, LoanApplication, LoanConfig, PaymentMethod, WithdrawalRequest
from .forms import PaymentMethodForm
from .models import User, PaymentMethod
from .forms import StaffUserForm, StaffPaymentMethodForm
import base64
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from .models import PaymentMethod
# ✅ ADD (top of views.py)
from io import BytesIO
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
import os


def normalize_upload_image(uploaded_file, *, max_side=1600, quality=78, out_format="WEBP"):
    """
    Normalize any phone image -> WEBP, resize, fix orientation, reduce size.
    Return: ContentFile ready to save into ImageField
    """
    if not uploaded_file:
        return None

    # Basic size guard (optional)
    if getattr(uploaded_file, "size", 0) > 10 * 1024 * 1024:  # 10MB
        raise ValueError("Image too large (max 10MB). Please upload a smaller photo.")

    # Open + fix EXIF rotate
    img = Image.open(uploaded_file)
    img = ImageOps.exif_transpose(img)

    # Convert to RGB (WEBP/JPG needs RGB)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize (keep ratio)
    w, h = img.size
    m = max(w, h)
    if m > max_side:
        scale = max_side / float(m)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # Save to memory
    buf = BytesIO()
    fmt = out_format.upper()

    if fmt == "WEBP":
        img.save(buf, format="WEBP", quality=quality, method=6)
        ext = "webp"
    else:
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        ext = "jpg"

    buf.seek(0)

    base = os.path.splitext(getattr(uploaded_file, "name", "upload"))[0]
    filename = f"{base}.{ext}"

    return ContentFile(buf.read(), name=filename)
User = get_user_model()


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
from django.contrib.auth.decorators import login_required

def choose_view(request):
    return render(request, "choose.html", {
        "is_auth": request.user.is_authenticated
    })


def login_view(request):
    """
    Login with phone + password (phone is USERNAME_FIELD).
    """
    if request.method == "POST":
        phone = (request.POST.get("phone") or "").strip()
        password = request.POST.get("password") or ""

        user = authenticate(request, username=phone, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect("staff_dashboard")
            return redirect("dashboard")

        messages.error(request, "Wrong phone or password.")
        return render(request, "login.html")

    return render(request, "login.html")


def register_view(request):
    """
    Register with:
    - phone + password + confirm_password
    - must accept agreement (agree_accepted=1)
    """
    if request.method == "POST":
        phone = (request.POST.get("phone") or "").strip()
        password = request.POST.get("password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        agree_accepted = (request.POST.get("agree_accepted") or "0").strip()

        if not phone or not password or not confirm_password:
            messages.error(request, "Phone, password and confirm password are required.")
            return render(request, "register.html")

        # ✅ must accept agreement first
        if agree_accepted != "1":
            messages.error(request, "Please read and accept the User Agreement before registering.")
            return render(request, "register.html")

        # ✅ password must match
        if password != confirm_password:
            messages.error(request, "Password and Confirm Password do not match.")
            return render(request, "register.html")

        if User.objects.filter(phone=phone).exists():
            messages.error(request, "This phone is already used.")
            return render(request, "register.html")

        user = User.objects.create_user(phone=phone, password=password)
        login(request, user)
        return redirect("dashboard")

    return render(request, "register.html")


@login_required(login_url="login")
def dashboard_view(request):
    last_loan = (
        LoanApplication.objects
        .filter(user=request.user)
        .exclude(status="REJECTED")
        .order_by("-id")
        .first()
    )

    selfie_url = None
    if last_loan and last_loan.selfie_with_id:
        try:
            selfie_url = last_loan.selfie_with_id.url
        except Exception:
            selfie_url = None

    # ✅ notification count for template
    notif_msg = (getattr(request.user, "notification_message", "") or "").strip()
    notif_count = 1 if notif_msg else 0

    return render(request, "dashboard.html", {
        "selfie_url": selfie_url,
        "last_loan": last_loan,
        "notif_count": notif_count,
    })
import json
import urllib.request
from django.views.decorators.http import require_GET
@require_GET
def fx_rates_api(request):
    url = "https://open.er-api.com/v6/latest/USD"
    wanted = ["PHP","SAR","MYR","INR","PKR","IDR","VND","OMR","KES","AFN"]

    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))

        rates = data.get("conversion_rates") or data.get("rates") or {}

        filtered = {}
        for c in wanted:
            v = rates.get(c, None)
            # ensure numeric or None
            try:
                filtered[c] = float(v) if v is not None else None
            except Exception:
                filtered[c] = None

        return JsonResponse({
            "base": "USD",
            "updated": data.get("time_last_update_utc") or data.get("date") or "",
            "rates": filtered,
        })
    except Exception:
        return JsonResponse({"base":"USD","updated":"","rates":{}}, status=200)

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import LoanApplication, PaymentMethod

User = get_user_model()

# =========================
# STAFF DASHBOARD PAGES
# =========================
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import transaction

from django import forms
from .forms import StaffUserForm, StaffPaymentMethodForm


from datetime import datetime, time, timedelta
from django.utils import timezone
from .models import LoanApplication, WithdrawalRequest, PaymentMethod


from datetime import datetime, time, timedelta
from django.utils import timezone
from django.shortcuts import render
from django.contrib.auth import get_user_model

from .models import LoanApplication, WithdrawalRequest, PaymentMethod


def staff_dashboard(request):
    User = get_user_model()

    period = (request.GET.get("period") or "").strip().lower()

    now = timezone.localtime()
    today = now.date()

    def start_of_day(d):
        return timezone.make_aware(datetime.combine(d, time.min))

    def end_of_day(d):
        return timezone.make_aware(datetime.combine(d, time.max))

    # ---- build date range based on period ----
    start_dt = None
    end_dt = None

    if period == "today":
        start_dt = start_of_day(today)
        end_dt = end_of_day(today)

    elif period == "yesterday":
        d = today - timedelta(days=1)
        start_dt = start_of_day(d)
        end_dt = end_of_day(d)

    elif period == "this_week":
        week_start_date = today - timedelta(days=today.weekday())  # Monday
        start_dt = start_of_day(week_start_date)
        end_dt = end_of_day(today)

    elif period == "last_week":
        week_start_date = today - timedelta(days=today.weekday())
        last_week_end_date = week_start_date - timedelta(days=1)   # Sunday last week
        last_week_start_date = last_week_end_date - timedelta(days=6)  # Monday last week
        start_dt = start_of_day(last_week_start_date)
        end_dt = end_of_day(last_week_end_date)

    elif period == "this_month":
        month_start_date = today.replace(day=1)
        start_dt = start_of_day(month_start_date)
        end_dt = end_of_day(today)

    elif period == "last_month":
        first_this_month = today.replace(day=1)
        last_month_last_day = first_this_month - timedelta(days=1)
        last_month_start_date = last_month_last_day.replace(day=1)
        start_dt = start_of_day(last_month_start_date)
        end_dt = end_of_day(last_month_last_day)

    # ---- totals (filtered if period selected) ----
    if start_dt and end_dt:
        total_users = User.objects.filter(created_at__range=(start_dt, end_dt)).count()
        total_loans = LoanApplication.objects.filter(created_at__range=(start_dt, end_dt)).count()
        total_withdrawals = WithdrawalRequest.objects.filter(created_at__range=(start_dt, end_dt)).count()
        total_payment_methods = PaymentMethod.objects.filter(created_at__range=(start_dt, end_dt)).count()
    else:
        total_users = User.objects.count()
        total_loans = LoanApplication.objects.count()
        total_withdrawals = WithdrawalRequest.objects.count()
        total_payment_methods = PaymentMethod.objects.count()

    # ---- performance overview (keep your original logic) ----
    def start_of_day(d):
        return timezone.make_aware(datetime.combine(d, time.min))

    def end_of_day(d):
        return timezone.make_aware(datetime.combine(d, time.max))

    today_start = start_of_day(today)
    today_end = end_of_day(today)

    yday = today - timedelta(days=1)
    yday_start = start_of_day(yday)
    yday_end = end_of_day(yday)

    week_start_date = today - timedelta(days=today.weekday())
    week_start = start_of_day(week_start_date)

    last_week_end_date = week_start_date - timedelta(days=1)
    last_week_start_date = last_week_end_date - timedelta(days=6)
    last_week_start = start_of_day(last_week_start_date)
    last_week_end = end_of_day(last_week_end_date)

    month_start_date = today.replace(day=1)
    month_start = start_of_day(month_start_date)

    first_this_month = month_start_date
    last_month_last_day = first_this_month - timedelta(days=1)
    last_month_start_date = last_month_last_day.replace(day=1)
    last_month_start = start_of_day(last_month_start_date)
    last_month_end = end_of_day(last_month_last_day)

    reg_today = User.objects.filter(created_at__range=(today_start, today_end)).count()
    reg_yesterday = User.objects.filter(created_at__range=(yday_start, yday_end)).count()
    reg_this_week = User.objects.filter(created_at__gte=week_start).count()
    reg_last_week = User.objects.filter(created_at__range=(last_week_start, last_week_end)).count()
    reg_this_month = User.objects.filter(created_at__gte=month_start).count()
    reg_last_month = User.objects.filter(created_at__range=(last_month_start, last_month_end)).count()
    # =========================
    # Bar height scale (real numbers)
    # =========================
    values = [reg_today, reg_yesterday, reg_this_week, reg_last_week, reg_this_month, reg_last_month]
    maxv = max(values) if values else 0

    def scale_height(v, min_h=55, max_h=200):
        """
        min_h = កម្ពស់អប្បបរមា (កុំឲ្យ bar ទាបពេក)
        max_h = កម្ពស់អតិបរមា (កុំឲ្យ bar លើស card)
        """
        if maxv <= 0:
            return min_h
        return int(min_h + (v / maxv) * (max_h - min_h))

    h_today = scale_height(reg_today)
    h_yesterday = scale_height(reg_yesterday)
    h_this_week = scale_height(reg_this_week)
    h_last_week = scale_height(reg_last_week)
    h_this_month = scale_height(reg_this_month)
    h_last_month = scale_height(reg_last_month)
    

    context = {
        "period": period,

        "total_users": total_users,
        "total_loans": total_loans,
        "total_withdrawals": total_withdrawals,
        "total_payment_methods": total_payment_methods,

        "reg_today": reg_today,
        "reg_yesterday": reg_yesterday,
        "reg_this_week": reg_this_week,
        "reg_last_week": reg_last_week,
        "reg_this_month": reg_this_month,
        "reg_last_month": reg_last_month,
        "h_today": h_today,
        "h_yesterday": h_yesterday,
        "h_this_week": h_this_week,
        "h_last_week": h_last_week,
        "h_this_month": h_this_month,
        "h_last_month": h_last_month,
    }
    return render(request, "staff_dashboard.html", context)


@staff_member_required
def staff_users_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all().order_by("-id")
    if q:
        qs = qs.filter(phone__icontains=q)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "staff_users.html", {"page": page, "q": q})

@staff_member_required
def staff_user_detail_view(request, user_id):
    u = get_object_or_404(User, id=user_id)

    # ✅ ADD THIS
    pm, _ = PaymentMethod.objects.get_or_create(user=u)

    form = StaffUserForm(instance=u)
    pm_form = StaffPaymentMethodForm(instance=pm)

    return render(
    request,
    "staff_user_detail.html",
    {
        "u": u,
        "form": form,
        "pm": pm,          # ✅ ADD THIS (important)
        "pm_form": pm_form # keep
    }
)
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import redirect
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
@transaction.atomic
def staff_user_update(request, user_id):
    if request.method != "POST":
        return redirect("staff_users")

    u = User.objects.select_for_update().filter(id=user_id).first()
    if not u:
        return redirect("staff_users")

    # ---- keep old values for change detection ----
    old_notif = (u.notification_message or "")
    old_success = (u.success_message or "")

    # ---- update ONLY fields that staff_users.html actually posts ----
    u.account_status = (request.POST.get("account_status") or u.account_status)
    u.withdraw_otp = (request.POST.get("withdraw_otp") or "").strip()

    is_active_raw = (request.POST.get("is_active") or "").strip()
    if is_active_raw in ("True", "False"):
        u.is_active = (is_active_raw == "True")

    # messages
    u.notification_message = (request.POST.get("notification_message") or "").strip()
    u.success_message = (request.POST.get("success_message") or "").strip()

    # optional fields (won't break if not in this page)
    if "credit_score" in request.POST:
        cs = (request.POST.get("credit_score") or "").strip()
        if cs != "":
            try:
                u.credit_score = int(cs)
            except ValueError:
                messages.error(request, "Credit score មិនត្រឹមត្រូវ ❌")
                return redirect(request.META.get("HTTP_REFERER", "staff_users"))

    if "status_message" in request.POST:
        u.status_message = (request.POST.get("status_message") or "").strip()

    # balance (manual)
    bal = (request.POST.get("balance") or "").strip()
    if bal != "":
        try:
            u.balance = Decimal(bal)
        except (InvalidOperation, ValueError):
            messages.error(request, "Balance មិនត្រឹមត្រូវ ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_users"))

    # timestamps + unread flags
    if (u.notification_message or "") != old_notif:
        u.notification_updated_at = timezone.now()
        u.notification_is_read = False

    if (u.success_message or "") != old_success:
        u.success_message_updated_at = timezone.now()
        u.success_is_read = False

    u.save()

    messages.success(request, f"Saved {u.phone} ✅")
    return redirect(request.META.get("HTTP_REFERER", "staff_users"))


@staff_member_required
def staff_loans_view(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().upper()

    qs = LoanApplication.objects.select_related("user").all().order_by("-id")
    if q:
        qs = qs.filter(user__phone__icontains=q)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "staff_loans.html", {"page": page, "q": q, "status": status})

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required

from .models import LoanApplication

@staff_member_required
@require_POST
def staff_loan_status_update(request, loan_id):
    loan = get_object_or_404(LoanApplication.objects.select_related("user"), id=loan_id)

    status = (request.POST.get("status") or "").strip().upper()
    valid = {v for v, _ in LoanApplication.STATUS_CHOICES}

    if status not in valid:
        messages.error(request, "Invalid status ❌")
        return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    old_status = (loan.status or "").upper()

    # ✅ If changing to APPROVED (only once)
    if status == "APPROVED" and old_status != "APPROVED":
        user = loan.user

        try:
            current_balance = Decimal(str(user.balance or "0"))
        except Exception:
            current_balance = Decimal("0")

        user.balance = current_balance + loan.amount
        user.save(update_fields=["balance"])

    loan.status = status
    loan.save(update_fields=["status"])

    messages.success(request, f"Loan #{loan.id} status updated ✅")
    return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

@staff_member_required
def staff_loan_detail_view(request, loan_id):
    loan = get_object_or_404(LoanApplication.objects.select_related("user"), id=loan_id)
    return render(request, "staff_loan_detail.html", {"loan": loan})    

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404

from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone

@staff_member_required
@transaction.atomic
def staff_loan_update(request, loan_id):
    if request.method != "POST":
        return redirect("staff_loans")

    loan = (
        LoanApplication.objects
        .select_for_update()
        .select_related("user")
        .filter(id=loan_id)
        .first()
    )
    if not loan:
        messages.error(request, "Loan not found")
        return redirect("staff_loans")

    u = loan.user  # user row (phone)

    # =========================
    # 1) UPDATE USER PHONE
    # =========================
    new_phone = (request.POST.get("phone") or "").strip()
    if new_phone and new_phone != u.phone:
        # prevent duplicate phone
        if User.objects.filter(phone=new_phone).exclude(id=u.id).exists():
            messages.error(request, "Phone already used by another account ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))
        u.phone = new_phone
        u.save(update_fields=["phone"])

    # =========================
    # 2) UPDATE LOAN TEXT FIELDS
    # =========================
    loan.full_name = (request.POST.get("full_name") or "").strip()
    loan.current_living = (request.POST.get("current_living") or "").strip()
    loan.hometown = (request.POST.get("hometown") or "").strip()
    loan.income = (request.POST.get("income") or "").strip()
    loan.monthly_expenses = (request.POST.get("monthly_expenses") or "").strip()
    loan.guarantor_contact = (request.POST.get("guarantor_contact") or "").strip()
    loan.guarantor_current_living = (request.POST.get("guarantor_current_living") or "").strip()
    loan.identity_name = (request.POST.get("identity_name") or "").strip()
    loan.identity_number = (request.POST.get("identity_number") or "").strip()

    # Age
    age_raw = (request.POST.get("age") or "").strip()
    if age_raw:
        try:
            loan.age = int(age_raw)
        except ValueError:
            messages.error(request, "Age មិនត្រឹមត្រូវ ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # =========================
    # 3) UPDATE AMOUNT + TERM
    # =========================
    amount_raw = (request.POST.get("amount") or "").strip()
    term_raw = (request.POST.get("term_months") or "").strip()

    # amount
    if amount_raw:
        try:
            loan.amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Amount មិនត្រឹមត្រូវ ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # term months
    if term_raw:
        try:
            loan.term_months = int(term_raw)
        except ValueError:
            messages.error(request, "Term months មិនត្រឹមត្រូវ ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # Optional: restrict allowed terms (same as client apply)
    if loan.term_months not in (6, 12, 24, 36, 48, 60):
        messages.error(request, "Term months មិនត្រឹមត្រូវ (6/12/24/36/48/60) ❌")
        return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # =========================
    # 4) AUTO CALC MONTHLY REPAYMENT
    # =========================
    # Use saved snapshot rate on the loan; if missing, fallback to LoanConfig; else fallback default.
    rate = loan.interest_rate_monthly
    if rate is None:
        cfg = LoanConfig.objects.first()
        rate = Decimal(str(cfg.interest_rate_monthly)) if cfg else Decimal("0.0003")
        loan.interest_rate_monthly = rate

    total = loan.amount + (loan.amount * Decimal(str(rate)) * Decimal(loan.term_months))
    loan.monthly_repayment = total / Decimal(loan.term_months)

    # =========================
    # 5) STATUS
    # =========================
    status = (request.POST.get("status") or "").strip().upper()
    valid = {v for v, _ in LoanApplication.STATUS_CHOICES}

    if status in valid:
        old_status = (loan.status or "").upper()
        loan.status = status

        if status == "APPROVED" and old_status != "APPROVED":
            loan.approved_at = timezone.now()

        if status != "APPROVED":
            loan.approved_at = None

    # =========================
    # 6) FILES (optional)
    # =========================
    # income_proof can be any file -> keep original behavior (no convert)
    if request.FILES.get("income_proof"):
        loan.income_proof = request.FILES["income_proof"]

    # ✅ Images -> normalize/resize/convert to WEBP (only if new file uploaded)
    try:
        if request.FILES.get("id_front"):
            loan.id_front = normalize_upload_image(request.FILES["id_front"])
        if request.FILES.get("id_back"):
            loan.id_back = normalize_upload_image(request.FILES["id_back"])
        if request.FILES.get("selfie_with_id"):
            loan.selfie_with_id = normalize_upload_image(request.FILES["selfie_with_id"])
        if request.FILES.get("signature_image"):
            loan.signature_image = normalize_upload_image(request.FILES["signature_image"])
    except ValueError as e:
        # normalize_upload_image can raise "Image too large..." etc.
        messages.error(request, str(e))
        return redirect(request.META.get("HTTP_REFERER", "staff_loans"))
    except Exception:
        messages.error(request, "Image upload failed ❌ Please try another photo.")
        return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    loan.save()
    messages.success(request, f"Saved loan #{loan.id} ✅ (Monthly repayment auto-updated)")
    return redirect(request.META.get("HTTP_REFERER", "staff_loans"))


@staff_member_required
def staff_withdrawals_view(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().lower()

    qs = WithdrawalRequest.objects.select_related("user").all().order_by("-id")
    if q:
        qs = qs.filter(user__phone__icontains=q)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "staff_withdrawals.html", {"page": page, "q": q, "status": status})
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect
from django.contrib import messages

@staff_member_required
@transaction.atomic
def staff_withdrawal_update(request, wid):
    if request.method != "POST":
        return redirect("staff_withdrawals")

    w = WithdrawalRequest.objects.select_for_update().select_related("user").filter(id=wid).first()
    if not w:
        messages.error(request, "Withdrawal not found")
        return redirect("staff_withdrawals")

    u = w.user  # user row will be updated safely inside atomic

    old_status = (w.status or "").lower()
    new_status = (request.POST.get("status") or "").strip().lower()

    # update basic fields
    if new_status:
        w.status = new_status

    w.otp_required = (request.POST.get("otp_required") == "True")
    w.staff_otp = (request.POST.get("staff_otp") or "").strip()

    # handle refunded toggle from staff UI
    # (we will refund ONLY once)
    want_refunded = (request.POST.get("refunded") == "True")

    # ---- REFUND LOGIC (only once) ----
    should_refund = False

    # Case 1: Staff set status to rejected -> refund (if not refunded yet)
    if new_status == "rejected" and not w.refunded:
        should_refund = True

    # Case 2: Staff manually toggle refunded=True -> refund (if not refunded yet)
    if want_refunded and not w.refunded:
        should_refund = True

    if should_refund:
        try:
            amt = Decimal(str(w.amount or "0"))
        except (InvalidOperation, ValueError):
            amt = Decimal("0")

        if amt > 0:
            try:
                bal = Decimal(str(u.balance or "0"))
            except Exception:
                bal = Decimal("0")

            u.balance = bal + amt
            u.save(update_fields=["balance"])

        w.refunded = True
    else:
        # keep whatever staff selected if already refunded
        # (do not set back to False automatically)
        if w.refunded:
            w.refunded = True
        else:
            w.refunded = want_refunded  # usually False

    w.save()
    messages.success(request, f"Updated withdrawal #{w.id} ✅")
    return redirect(request.META.get("HTTP_REFERER", "staff_withdrawals"))


@staff_member_required
def staff_payment_methods_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = PaymentMethod.objects.select_related("user").all().order_by("-updated_at")
    if q:
        qs = qs.filter(user__phone__icontains=q)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "staff_payment_methods.html", {"page": page, "q": q})


@staff_member_required
@transaction.atomic
def staff_payment_method_update(request, pm_id):
    if request.method != "POST":
        return redirect("staff_payment_methods")

    pm = PaymentMethod.objects.select_for_update().filter(id=pm_id).first()
    if not pm:
        messages.error(request, "Payment method not found ❌")
        return redirect("staff_payment_methods")

    # ✅ Staff អាចកែបានជានិច្ច ទោះ locked = True ក៏ដោយ (គ្មានការកំណត់ block នៅទីនេះទេ)
    form = StaffPaymentMethodForm(request.POST, instance=pm)

    if not form.is_valid():
        # ✅ នេះជាមូលហេតុធំៗដែល PayPal មិន save (email មិនត្រឹមត្រូវ) តែ UI មិនបង្ហាញ error
        err = form.errors.as_text()
        messages.error(request, f"Form error ❌ {err}")
        return redirect(request.META.get("HTTP_REFERER", "staff_payment_methods"))

    obj = form.save(commit=False)

    # ✅ Save locked from dropdown (On/Off) ដោយដៃ (ព្រោះ form មិនមាន field locked)
    locked_value = (request.POST.get("locked") or "").strip()
    obj.locked = True if locked_value == "True" else False

    obj.save()
    messages.success(request, "Saved ✅")
    return redirect(request.META.get("HTTP_REFERER", "staff_payment_methods"))


@login_required(login_url="login")
def profile_view(request):
    return render(request, "profile.html")


@login_required(login_url="login")
def credit_score_view(request):
    return render(request, "credit_score.html")


@login_required(login_url="login")
def transactions_view(request):
    # show ONLY 2 types: Payment sent (paid) + Rejected
    withdrawals = (
        WithdrawalRequest.objects
        .filter(user=request.user, status__in=["paid", "rejected"])
        .order_by("-created_at")[:20]
    )

    return render(request, "transaction.html", {
        "withdrawals": withdrawals
    }) # your template is singular


from datetime import timedelta
from django.utils import timezone
from dateutil.relativedelta import relativedelta

@login_required(login_url="login")
def payment_schedule_view(request):
    latest_loan = (
        LoanApplication.objects
        .filter(user=request.user, status="APPROVED")
        .order_by("-approved_at", "-id")
        .first()
    )

    schedules = []
    if latest_loan:
        start = latest_loan.approved_at or latest_loan.created_at or timezone.now()
        first_due = start + timedelta(days=15)

        for i in range(int(latest_loan.term_months or 0)):
            due = first_due + relativedelta(months=i)
            schedules.append({
                "due_date": due.strftime("%d/%m/%Y"),
                "loan_amount": latest_loan.amount,
                "term_months": latest_loan.term_months,
                "repayment": latest_loan.monthly_repayment,
                "interest_rate": latest_loan.interest_rate_monthly,
            })

    return render(request, "payment_schedule.html", {
        "latest_loan": latest_loan,
        "schedules": schedules,
    })


@login_required(login_url="login")
def contact_view(request):
    return render(request, "contactus.html")


@login_required(login_url="login")
def loan_apply_view(request):
    # lock if not rejected
    existing = (
        LoanApplication.objects
        .filter(user=request.user)
        .exclude(status="REJECTED")
        .order_by("-id")
        .first()
    )

    if request.method != "POST":
        return render(request, "loan_apply.html", {"locked": existing is not None, "loan": existing})

    if existing:
        messages.info(request, "You already submitted. Waiting for review.")
        return render(request, "loan_apply.html", {"locked": True, "loan": existing})

    full_name = (request.POST.get("full_name") or "").strip()
    age_raw = (request.POST.get("age") or "").strip()
    current_living = (request.POST.get("current_living") or "").strip()
    hometown = (request.POST.get("hometown") or "").strip()
    income = (request.POST.get("income") or "").strip()
    monthly_expenses = (request.POST.get("monthly_expenses") or "").strip()
    guarantor_contact = (request.POST.get("guarantor_contact") or "").strip()
    guarantor_current_living = (request.POST.get("guarantor_current_living") or "").strip()
    identity_name = (request.POST.get("identity_name") or "").strip()
    identity_number = (request.POST.get("identity_number") or "").strip()
    signature_data = (request.POST.get("signature_data") or "").strip()

    loan_amount_raw = (request.POST.get("loan_amount") or "").strip()
    term_raw = (request.POST.get("loan_terms") or "").strip()

    # ✅ BUG FIX: your HTML uses checkboxes name="loan_purposes"
    # request.POST.get() only gets ONE item -> must use getlist()
    loan_purposes = request.POST.getlist("loan_purposes")  # list of selected

    # files
    id_front_raw = request.FILES.get("id_front")
    id_back_raw = request.FILES.get("id_back")
    selfie_raw = request.FILES.get("selfie_with_id")
    income_proof = request.FILES.get("income_proof")

    # required fields validate
    if not (
        full_name and age_raw and current_living and hometown and monthly_expenses
        and guarantor_contact and guarantor_current_living and identity_name and identity_number
    ):
        messages.error(request, "Please fill all required fields.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    if not (id_front_raw and id_back_raw and selfie_raw):
        messages.error(request, "Please upload Front/Back/Selfie ID images.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    # ✅ signature required (your JS blocks too, but server must validate)
    if not signature_data.startswith("data:image"):
        messages.error(request, "Please draw your signature first.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    # parse age/amount/term
    try:
        age = int(age_raw)
    except ValueError:
        messages.error(request, "Invalid age.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    try:
        amount = Decimal(loan_amount_raw)
    except (InvalidOperation, ValueError):
        messages.error(request, "Invalid loan amount.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    try:
        term_months = int(term_raw)
    except ValueError:
        messages.error(request, "Please choose loan terms.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    if term_months not in (6, 12, 24, 36, 48, 60):
        messages.error(request, "Invalid loan terms.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    # config + rate
    cfg = LoanConfig.objects.first()
    if cfg:
        if amount < Decimal(str(cfg.min_amount)) or amount > Decimal(str(cfg.max_amount)):
            messages.error(request, f"Loan amount must be between {cfg.min_amount} and {cfg.max_amount}.")
            return render(request, "loan_apply.html", {"locked": False, "loan": None})
        rate = Decimal(str(cfg.interest_rate_monthly))
    else:
        rate = Decimal("0.0003")

    total = amount + (amount * rate * Decimal(term_months))
    monthly = total / Decimal(term_months)

    # ✅ Normalize images (convert/resize/compress)
    try:
        id_front = normalize_upload_image(id_front_raw, max_side=1600, quality=78, out_format="WEBP")
        id_back = normalize_upload_image(id_back_raw, max_side=1600, quality=78, out_format="WEBP")
        selfie_with_id = normalize_upload_image(selfie_raw, max_side=1600, quality=78, out_format="WEBP")
    except ValueError as e:
        messages.error(request, str(e))
        return render(request, "loan_apply.html", {"locked": False, "loan": None})
    except Exception:
        messages.error(request, "Image upload error. Please try again with a different photo.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    # ✅ Signature base64 -> file (safe)
    try:
        header, b64 = signature_data.split(";base64,", 1)
        sig_file = ContentFile(base64.b64decode(b64), name=f"signature_{request.user.id}.png")
    except Exception:
        messages.error(request, "Signature error. Please clear and draw again.")
        return render(request, "loan_apply.html", {"locked": False, "loan": None})

    LoanApplication.objects.create(
        user=request.user,
        full_name=full_name,
        age=age,
        current_living=current_living,
        hometown=hometown,
        income=income,
        monthly_expenses=monthly_expenses,
        guarantor_contact=guarantor_contact,
        guarantor_current_living=guarantor_current_living,
        identity_name=identity_name,
        identity_number=identity_number,

        income_proof=income_proof,

        id_front=id_front,
        id_back=id_back,
        selfie_with_id=selfie_with_id,
        signature_image=sig_file,

        amount=amount,
        term_months=term_months,
        interest_rate_monthly=rate,
        monthly_repayment=monthly,
        status="PENDING",

        # ✅ correct list
        loan_purposes=loan_purposes or [],
    )

    messages.success(request, "Submitted successfully. Waiting for review.")
    url = reverse("payment_method") + "?next=quick_loan"
    return redirect(url)




@login_required(login_url="login")
def wallet_view(request):
    last = WithdrawalRequest.objects.filter(user=request.user).order_by("-id").first()
    items = WithdrawalRequest.objects.filter(user=request.user).order_by("-id")[:20]
    return render(request, "wallet.html", {"last_withdrawal": last, "withdrawals": items})


@login_required(login_url="login")
def withdraw_status(request):
    last = WithdrawalRequest.objects.filter(user=request.user).order_by("-id").first()
    if not last:
        return JsonResponse({"ok": True, "has": False})

    return JsonResponse({
        "ok": True,
        "has": True,
        "id": last.id,
        "status": last.status,
        "updated_at": last.updated_at.isoformat(),
    })


@login_required(login_url="login")
def quick_loan_view(request):
    loan = (
        LoanApplication.objects
        .filter(user=request.user)
        .order_by("-id")
        .first()
    )

    done = request.GET.get("done") == "1"
    return render(request, "quick_loan.html", {"loan": loan, "done": done})

@login_required(login_url="login")
@require_POST
def withdraw_create(request):
    # ✅ allow withdraw only when account is ACTIVE
    st = (getattr(request.user, "account_status", "") or "").strip().upper()
    if st != "ACTIVE":
        return JsonResponse({"ok": False, "error": "account_not_active"})
    otp = (request.POST.get("otp") or "").strip()
    if not otp:
        return JsonResponse({"ok": False, "error": "otp_required"})

    staff_otp = (getattr(request.user, "withdraw_otp", "") or "").strip()
    if not staff_otp or otp != staff_otp:
        return JsonResponse({"ok": False, "error": "otp_wrong"})

    existing = WithdrawalRequest.objects.filter(
        user=request.user,
        status__in=["processing", "waiting", "reviewed"]
    ).order_by("-id").first()
    if existing:
        return JsonResponse({"ok": True, "already": True})

    bal = getattr(request.user, "balance", 0) or 0
    try:
        bal = Decimal(str(bal))
    except Exception:
        bal = Decimal("0")

    if bal <= 0:
        return JsonResponse({"ok": False, "error": "insufficient"})

    amount_raw = (request.POST.get("amount") or "").strip()
    if not amount_raw:
        return JsonResponse({"ok": False, "error": "amount_required"})

    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_amount"})

    if amount <= 0:
        return JsonResponse({"ok": False, "error": "invalid_amount"})

    if amount > bal:
        return JsonResponse({"ok": False, "error": "exceed"})

    # Deduct immediately
    request.user.balance = bal - amount
    request.user.save(update_fields=["balance"])

    WithdrawalRequest.objects.create(
        user=request.user,
        amount=amount,
        currency="PHP",
        status="processing",
    )

    return JsonResponse({"ok": True})


@login_required(login_url="login")
def realtime_state(request):
    user = request.user
    bal = getattr(user, "balance", 0) or 0

    status = (getattr(user, "account_status", "active") or "active").lower()
    msg = (getattr(user, "status_message", "") or "").strip()

    last = WithdrawalRequest.objects.filter(user=user).order_by("-id").first()
    otp_required = (getattr(user, "withdraw_otp", "") or "").strip()

    # ✅ NOTIFICATION COUNT (dot/badge)
    alert_msg = (getattr(user, "notification_message", "") or "").strip()
    success_msg = (getattr(user, "success_message", "") or "").strip()

    notif_count = (
    (1 if alert_msg and not getattr(user, "notification_is_read", False) else 0) +
    (1 if success_msg and not getattr(user, "success_is_read", False) else 0)
)

    return JsonResponse({
        "ok": True,
        "account_status": status,
        "status_message": msg,
        "balance": str(bal),

        # ✅ add this
        "notif_count": notif_count,

        "otp_required": True if otp_required else False,
        "withdrawal": {
            "id": last.id if last else None,
            "status": last.status if last else "",
            "status_label": last.get_status_display() if last else "",
            "updated_at": last.updated_at.isoformat() if last else "",
        }
    })


@login_required(login_url="login")
def payment_method_view(request):
    obj, _ = PaymentMethod.objects.get_or_create(user=request.user)

    if request.method == "POST" and obj.locked:
        messages.error(request, "Locked. Please contact staff to update.")
        form = PaymentMethodForm(instance=obj)
        return render(request, "payment_method.html", {"form": form, "locked": True, "saved": True})

    if request.method == "POST":
        form = PaymentMethodForm(request.POST, instance=obj)
        if form.is_valid():
            pm = form.save(commit=False)
            pm.user = request.user
            pm.locked = True
            pm.save()

            messages.success(request, "Saved successfully.")

            next_page = (request.GET.get("next") or "").strip()
            if next_page == "quick_loan":
                return redirect(reverse("quick_loan") + "?done=1")

            return redirect("payment_method")

        return render(request, "payment_method.html", {"form": form, "locked": obj.locked, "saved": False})

    form = PaymentMethodForm(instance=obj)
    saved = bool(obj.wallet_name or obj.wallet_phone or obj.bank_name or obj.bank_account or obj.paypal_email)
    return render(request, "payment_method.html", {"form": form, "locked": obj.locked, "saved": saved})


@login_required(login_url="login")
@require_POST
def verify_withdraw_otp(request):
    otp = (request.POST.get("otp") or "").strip()
    staff_otp = (getattr(request.user, "withdraw_otp", "") or "").strip()

    if not otp:
        return JsonResponse({"ok": False, "error": "otp_required"})
    if not staff_otp or otp != staff_otp:
        return JsonResponse({"ok": False, "error": "otp_wrong"})
    return JsonResponse({"ok": True})


@login_required(login_url="login")
def account_status_api(request):
    u = request.user
    status = (getattr(u, "account_status", "") or "active").strip().lower()
    msg = (getattr(u, "status_message", "") or "").strip()

    if not msg and status != "active":
        msg_map = {
            "frozen": "Your account has been FROZEN. Please contact company department!",
            "rejected": "Your account has been REJECTED. Please contact company department!",
            "pending": "Your account is under review. Please wait.",
            "error": "System error. Please contact company department!",
        }
        msg = msg_map.get(status, "Please contact company department!")

    return JsonResponse({
        "status": status,
        "status_label": status.upper(),
        "message": msg,
        "balance": str(getattr(u, "balance", "0.00")),
    })


from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

@login_required(login_url="login")
def notifications_view(request):
    alert_msg = (request.user.notification_message or "").strip()
    alert_at = request.user.notification_updated_at

    success_msg = (request.user.success_message or "").strip()
    success_at = request.user.success_message_updated_at

    changed = []

    if alert_msg and not request.user.notification_is_read:
        request.user.notification_is_read = True
        changed.append("notification_is_read")

    if success_msg and not request.user.success_is_read:
        request.user.success_is_read = True
        changed.append("success_is_read")

    if changed:
        request.user.save(update_fields=changed)

    # ✅ build list + sort newest first
    items = []
    if success_msg:
        items.append({
            "kind": "success",
            "title": "Congratulations",
            "msg": success_msg,
            "at": success_at,
        })
    if alert_msg:
        items.append({
            "kind": "alert",
            "title": "Important Notice",
            "msg": alert_msg,
            "at": alert_at,
        })

    tz = timezone.get_current_timezone()
    min_dt = timezone.make_aware(datetime.min, tz)
    items.sort(key=lambda x: x["at"] or min_dt, reverse=True)

    return render(request, "notifications.html", {
        "items": items,
    })


# show status ONLY when loan exists AND payment method locked
from django.utils import timezone
from datetime import timedelta

@login_required(login_url="login")
def loan_status_api(request):
    loan = (
        LoanApplication.objects
        .filter(user=request.user)
        .order_by("-id")
        .first()
    )

    pm = PaymentMethod.objects.filter(user=request.user).first()
    pm_ok = bool(pm and pm.locked)

    if not loan or not pm_ok:
        return JsonResponse({"ok": True, "show": False})

    # ✅ AUTO STEP LOGIC (ONLY when DB status is still PENDING)
    # Step 1: 0–3h
    # Step 2: >=3h (stays step2 until admin updates to APPROVED/PAID etc)
    ui_status = loan.status
    if loan.status == "PENDING" and loan.created_at:
        age = timezone.now() - loan.created_at
        if age >= timedelta(hours=3):
            ui_status = "REVIEW"  # show Step 2 in UI

    # ✅ Create a label for UI (don't break existing frontend)
    label_map = {
        "PENDING": "Pending",
        "REVIEW": "In Review",
        "APPROVED": "Approved",
        "REJECTED": "Rejected",
        "PAID": "Paid",
    }
    ui_label = label_map.get(ui_status, ui_status)

    return JsonResponse({
        "ok": True,
        "show": True,
        "status": ui_status,
        "status_label": ui_label,
    })
@login_required(login_url="login")
def contract_view(request):
    # ✅ use latest loan (ignore rejected)
    loan = (
        LoanApplication.objects
        .filter(user=request.user)
        .exclude(status="REJECTED")
        .order_by("-id")
        .first()
    )

    # default safe values (no error even if no loan yet)
    ctx = {
        "full_name": getattr(loan, "full_name", "") or "",
        "phone": getattr(request.user, "phone", "") or "",
        "current_living": getattr(loan, "current_living", "") or "",
        "amount": str(getattr(loan, "amount", "") or "0.00"),
        "term_months": getattr(loan, "term_months", "") or "",
        "interest_rate": "0.03",  # ✅ change later easily
        "monthly_repayment": str(getattr(loan, "monthly_repayment", "") or "0.00"),
    }
    return render(request, "contract.html", ctx)
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test

from .models import LoanApplication

def is_staff_user(u):
    return u.is_authenticated and u.is_staff

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test

from .models import LoanApplication
from .forms import StaffLoanApplicationForm

def is_staff_user(u):
    return u.is_authenticated and u.is_staff
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    # 🔥 clear all messages BEFORE logout
    storage = messages.get_messages(request)
    list(storage)

    logout(request)

    # 🔥 clear again (double safety)
    storage = messages.get_messages(request)
    list(storage)

    return redirect("login")
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST

@staff_member_required
@require_POST
def staff_logout(request):
    logout(request)
    return redirect("/admin/login/?next=/staff/")   

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def agreement(request):
    return render(request, "agreement.html")