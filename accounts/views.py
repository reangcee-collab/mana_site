from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from .models import LoanApplication, LoanConfig, PaymentMethod, WithdrawalRequest
from .forms import PaymentMethodForm
from .models import User, PaymentMethod
from .forms import StaffUserForm, StaffPaymentMethodForm
import base64
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from .models import PaymentMethod

User = get_user_model()


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
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


@staff_member_required
def staff_dashboard_view(request):
    # totals
    total_users = User.objects.count()
    total_loans = LoanApplication.objects.count()
    total_withdrawals = WithdrawalRequest.objects.count()
    total_payment_methods = PaymentMethod.objects.count()

    return render(request, "staff_dashboard.html", {
        "total_users": total_users,
        "total_loans": total_loans,
        "total_withdrawals": total_withdrawals,
        "total_payment_methods": total_payment_methods,
    })


@staff_member_required
def staff_users_view(request):
    q = (request.GET.get("q") or "").strip()
    qs = User.objects.all().order_by("-id")
    if q:
        qs = qs.filter(phone__icontains=q)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "staff_users.html", {"page": page, "q": q})
from .models import User, PaymentMethod

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

    # USER FORM
    form = StaffUserForm(request.POST, instance=u)
    if not form.is_valid():
        messages.error(request, "Form error ❌")
        return redirect(request.META.get("HTTP_REFERER", "staff_users"))

    obj = form.save(commit=False)

    # BALANCE
    bal = (request.POST.get("balance") or "").strip()
    if bal != "":
        try:
            obj.balance = Decimal(bal)
        except (InvalidOperation, ValueError):
            messages.error(request, "Balance មិនត្រឹមត្រូវ")
            return redirect(request.META.get("HTTP_REFERER", "staff_users"))

    # MESSAGE TIMESTAMP
    changed = set(form.changed_data)

    if "notification_message" in changed:
        obj.notification_updated_at = timezone.now()
        obj.notification_is_read = False

    if "success_message" in changed:
        obj.success_message_updated_at = timezone.now()
        obj.success_is_read = False

    obj.save()

    # ✅ PAYMENT FORM: update ONLY if staff actually submitted payment fields
    PM_KEYS = {"bank_name", "bank_account", "wallet_name", "wallet_phone", "paypal_email"}
    if any(k in request.POST for k in PM_KEYS):
        payment, _ = PaymentMethod.objects.get_or_create(user=u)
        payment_form = StaffPaymentMethodForm(request.POST, instance=payment)
        if payment_form.is_valid():
            payment_form.save()
        else:
            messages.error(request, "Payment form error ❌")
            return redirect(request.META.get("HTTP_REFERER", "staff_users"))

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

    loan = LoanApplication.objects.select_for_update().filter(id=loan_id).first()
    if not loan:
        messages.error(request, "Loan not found")
        return redirect("staff_loans")

    # ✅ Save text fields (because template now sends name=...)
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
            messages.error(request, "Age មិនត្រឹមត្រូវ")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # Amount
    amount_raw = (request.POST.get("amount") or "").strip()
    if amount_raw:
        try:
            loan.amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Amount មិនត្រឹមត្រូវ")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # Term months
    term_raw = (request.POST.get("term_months") or "").strip()
    if term_raw:
        try:
            loan.term_months = int(term_raw)
        except ValueError:
            messages.error(request, "Term months មិនត្រឹមត្រូវ")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # Monthly repayment (optional)
    mr_raw = (request.POST.get("monthly_repayment") or "").strip()
    if mr_raw:
        try:
            loan.monthly_repayment = Decimal(mr_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Monthly repayment មិនត្រឹមត្រូវ")
            return redirect(request.META.get("HTTP_REFERER", "staff_loans"))

    # ✅ Status
    status = (request.POST.get("status") or "").strip().upper()
    valid = {v for v, _ in LoanApplication.STATUS_CHOICES}
    if status in valid:
        loan.status = status

    # ✅ Files (uploads)
    if request.FILES.get("income_proof"):
        loan.income_proof = request.FILES["income_proof"]

    if request.FILES.get("id_front"):
        loan.id_front = request.FILES["id_front"]
    if request.FILES.get("id_back"):
        loan.id_back = request.FILES["id_back"]
    if request.FILES.get("selfie_with_id"):
        loan.selfie_with_id = request.FILES["selfie_with_id"]
    if request.FILES.get("signature_image"):
        loan.signature_image = request.FILES["signature_image"]

    loan.save()
    messages.success(request, f"Saved loan #{loan.id} ✅")
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
        return redirect("staff_payment_methods")

    form = StaffPaymentMethodForm(request.POST, instance=pm)
    if form.is_valid():
        form.save()
    return redirect(request.META.get("HTTP_REFERER", "staff_payment_methods"))



@login_required(login_url="login")
def profile_view(request):
    return render(request, "profile.html")


@login_required(login_url="login")
def credit_score_view(request):
    return render(request, "credit_score.html")


@login_required(login_url="login")
def transactions_view(request):
    return render(request, "transaction.html")  # your template is singular


@login_required(login_url="login")
def payment_schedule_view(request):
    return render(request, "payment_schedule.html")


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

    id_front = request.FILES.get("id_front")
    id_back = request.FILES.get("id_back")
    selfie_with_id = request.FILES.get("selfie_with_id")
    loan_purpose = (request.POST.get("loan_purposes") or "").strip()

    if not (
    full_name and age_raw and current_living and hometown and monthly_expenses
    and guarantor_contact and guarantor_current_living and identity_name and identity_number and signature_data
):
        messages.error(request, "Please fill all required fields.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})

    if not (id_front and id_back and selfie_with_id):
        messages.error(request, "Please upload Front/Back/Selfie ID images.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})

    try:
        age = int(age_raw)
    except ValueError:
        messages.error(request, "Invalid age.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})

    try:
        amount = Decimal(loan_amount_raw)
    except (InvalidOperation, ValueError):
        messages.error(request, "Invalid loan amount.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})

    try:
        term_months = int(term_raw)
    except ValueError:
        messages.error(request, "Please choose loan terms.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})

    if term_months not in (6, 12, 24, 36, 48, 60):
        messages.error(request, "Invalid loan terms.")
        return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})
    cfg = LoanConfig.objects.first()
    if cfg:
        if amount < Decimal(str(cfg.min_amount)) or amount > Decimal(str(cfg.max_amount)):
            messages.error(request, f"Loan amount must be between {cfg.min_amount} and {cfg.max_amount}.")
            return render(request, "loan_apply.html", {
    "locked": False,
    "loan": None,
    "loan_purpose": loan_purpose,
})
        rate = Decimal(str(cfg.interest_rate_monthly))
    else:
        rate = Decimal("0.0003")  # 0.03%

    total = amount + (amount * rate * Decimal(term_months))
    monthly = total / Decimal(term_months)
    sig_file = None
    if signature_data.startswith("data:image"):
        header, b64 = signature_data.split(";base64,", 1)
    sig_file = ContentFile(base64.b64decode(b64), name=f"signature_{request.user.id}.png")

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
        id_front=id_front,
        id_back=id_back,
        selfie_with_id=selfie_with_id,
        signature_image=sig_file,
        amount=amount,
        term_months=term_months,
        interest_rate_monthly=rate,
        monthly_repayment=monthly,
        status="PENDING",
        loan_purposes=[loan_purpose] if loan_purpose else [],
)

    messages.success(request, "Submitted successfully. Waiting for review.")

    # correct redirect to payment_method with query next=quick_loan
    url = reverse("payment_method") + "?next=quick_loan"
    return redirect(url)


def logout_view(request):
    logout(request)
    return redirect("login")


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
        currency="PKR",
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

    return render(request, "notifications.html", {
        "alert_msg": alert_msg,
        "alert_at": alert_at,
        "success_msg": success_msg,
        "success_at": success_at,
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