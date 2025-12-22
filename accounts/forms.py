from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Profile

User = get_user_model()

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password1", "password2")

    def clean_email(self):
        email = (self.cleaned_data["email"] or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        if commit:
            user.save()
        return user

class ProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=False)

    class Meta:
        model = Profile
        fields = ["avatar", "phone", "company_name", "industry", "custom_industry", "company_description"]
        widgets = {
            "company_description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # preload user name fields
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name

    def clean_company_description(self):
        desc = (self.cleaned_data.get("company_description") or "").strip()
        if not desc:
            return desc
        words = [w for w in desc.split() if w.strip()]
        if len(words) > 200:
            raise forms.ValidationError("Company description must be within 200 words.")
        return desc

    def clean(self):
        cleaned = super().clean()
        industry = (cleaned.get("industry") or "").strip()
        custom = (cleaned.get("custom_industry") or "").strip()

        if industry == "other" and not custom:
            self.add_error("custom_industry", "Please specify your industry.")
        if industry != "other":
            cleaned["custom_industry"] = ""  # keep DB clean
        return cleaned

    def save(self, commit=True):
        # update user fields
        self.user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        self.user.last_name = (self.cleaned_data.get("last_name") or "").strip()
        if commit:
            self.user.save()

        profile = super().save(commit=commit)
        return profile
