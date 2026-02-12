from django.urls import path
from . import views
from .views import staff_user_update

urlpatterns = [
    path("", views.choose_view, name="choose"),
    path("choose/", views.choose_view, name="choose"),

    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("staff-dashboard/", views.staff_dashboard, name="staff_dashboard"),
    path("profile/", views.profile_view, name="profile"),
    path("credit-score/", views.credit_score_view, name="credit_score"),
    path("transactions/", views.transactions_view, name="transactions"),
    path("payment-schedule/", views.payment_schedule_view, name="payment_schedule"),

    path("loan-apply/", views.loan_apply_view, name="loan_apply"),
    path("quick-loan/", views.quick_loan_view, name="quick_loan"),

    path("wallet/", views.wallet_view, name="wallet"),
    path("wallet/withdraw/", views.withdraw_create, name="withdraw_create"),
    path("wallet/status/", views.withdraw_status, name="withdraw_status"),
    path("wallet/verify-otp/", views.verify_withdraw_otp, name="verify_withdraw_otp"),

    path("api/realtime/", views.realtime_state, name="realtime_state"),
    path("api/account-status/", views.account_status_api, name="account_status_api"),
    path("api/fx/", views.fx_rates_api, name="fx_rates_api"),

    path("contact/", views.contact_view, name="contact"),
    path("payment-method/", views.payment_method_view, name="payment_method"),
    path("notifications/", views.notifications_view, name="notifications"),
    path("api/loan-status/", views.loan_status_api, name="loan_status_api"),
    path("contract/", views.contract_view, name="contract"),
    # =========================
# STAFF ROUTES (clean, no duplicate)
# =========================
path("staff/", views.staff_dashboard, name="staff_dashboard"),

path("staff/users/", views.staff_users_view, name="staff_users"),
path("staff/users/<int:user_id>/", views.staff_user_detail_view, name="staff_user_detail"),
path("staff/users/<int:user_id>/update/", views.staff_user_update, name="staff_user_update"),

path("staff/loans/", views.staff_loans_view, name="staff_loans"),
path("staff/loans/<int:loan_id>/", views.staff_loan_detail_view, name="staff_loan_detail"),
path("staff/loans/<int:loan_id>/update/", views.staff_loan_update, name="staff_loan_update"),

path("staff/withdrawals/", views.staff_withdrawals_view, name="staff_withdrawals"),
path("staff/withdrawals/<int:wid>/update/", views.staff_withdrawal_update, name="staff_withdrawal_update"),

path("staff/payment-methods/", views.staff_payment_methods_view, name="staff_payment_methods"),
path("staff/payment-methods/<int:pm_id>/update/", views.staff_payment_method_update, name="staff_payment_method_update"),
path("staff/logout/", views.staff_logout, name="staff_logout"),
path("staff/loans/<int:loan_id>/status/", views.staff_loan_status_update, name="staff_loan_status_update"),
    path("agreement/", views.agreement, name="agreement"),
]