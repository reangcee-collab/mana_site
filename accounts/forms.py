from django import forms
from django.core.exceptions import ValidationError
from .models import PaymentMethod
from django.utils.html import format_html
from django import forms
from .models import LoanApplication

class StaffLoanApplicationForm(forms.ModelForm):
    class Meta:
        model = LoanApplication
        fields = [
            # info
            "full_name", "age", "current_living", "hometown",
            "income", "monthly_expenses",
            "guarantor_contact", "guarantor_current_living",
            "identity_name", "identity_number",

            # loan
            "amount", "term_months",
            "status",

            # uploads
            "income_proof",
            "id_front", "id_back", "selfie_with_id", "signature_image",
        ]

class AdminImagePreviewWidget(forms.ClearableFileInput):
    """
    Show image preview instead of text link in admin form.
    """
    def __init__(self, label="Image", *args, **kwargs):
        self.label = label
        super().__init__(*args, **kwargs)

    def format_value(self, value):
        return value

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        # Add preview html
        if value and hasattr(value, "url"):
            ctx["preview_html"] = format_html(
                '<div style="margin:6px 0 10px;">'
                '<img src="{}" style="height:110px;border-radius:10px;object-fit:cover;border:1px solid #ddd;" />'
                '</div>',
                value.url
            )
        else:
            ctx["preview_html"] = ""
        return ctx

    def render(self, name, value, attrs=None, renderer=None):
        ctx = self.get_context(name, value, attrs)
        # preview on top + normal file input below (Change:)
        html = "{}{}".format(ctx.get("preview_html", ""), super().render(name, value, attrs, renderer))
        return html


class LoanApplicationAdminForm(forms.ModelForm):
    class Meta:
        model = LoanApplication
        fields = "__all__"
        widgets = {
            "id_front": AdminImagePreviewWidget(label="ID Front"),
            "id_back": AdminImagePreviewWidget(label="ID Back"),
            "selfie_with_id": AdminImagePreviewWidget(label="Selfie + ID"),
            "signature_image": AdminImagePreviewWidget(label="Signature"),
        }

class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["wallet_name","wallet_phone","bank_name","bank_account","paypal_email"]

    def clean(self):
        cleaned = super().clean()

        wallet_name  = (cleaned.get("wallet_name") or "").strip()
        wallet_phone = (cleaned.get("wallet_phone") or "").strip()
        bank_name    = (cleaned.get("bank_name") or "").strip()
        bank_account = (cleaned.get("bank_account") or "").strip()
        paypal_email = (cleaned.get("paypal_email") or "").strip()  # optional

        wallet_any = bool(wallet_name or wallet_phone)
        bank_any   = bool(bank_name or bank_account)

        # If user starts wallet, require both
        if wallet_any and not (wallet_name and wallet_phone):
            raise ValidationError("Mobile Wallet requires BOTH account name and phone number.")

        # If user starts bank, require both
        if bank_any and not (bank_name and bank_account):
            raise ValidationError("Bank requires BOTH account name and account number.")

        # Must have at least one completed method (wallet or bank)
        wallet_complete = bool(wallet_name and wallet_phone)
        bank_complete   = bool(bank_name and bank_account)

        if not (wallet_complete or bank_complete):
            raise ValidationError("Please complete Mobile Wallet or Bank before saving. PayPal is optional.")

        # keep paypal optional (no extra rule)
        cleaned["wallet_name"] = wallet_name
        cleaned["wallet_phone"] = wallet_phone
        cleaned["bank_name"] = bank_name
        cleaned["bank_account"] = bank_account
        cleaned["paypal_email"] = paypal_email
        return cleaned
from .models import User, PaymentMethod

class StaffUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "account_status",
            "withdraw_otp",
            "notification_message",
            "success_message",
            "status_message",
            "is_active",
        ]


class StaffPaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = [
            "bank_name",
            "bank_account",
            "wallet_name",
            "wallet_phone",
            "paypal_email",
        ]