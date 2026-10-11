from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "role")
        labels = {"email": "Демонстрационный email", "role": "Роль"}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not email.endswith("@demo.invalid"):
            raise forms.ValidationError("Для демо используйте адрес @demo.invalid. Реальные письма не отправляются.")
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Этот demo адрес уже зарегистрирован.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.is_active = False
        if commit:
            user.save()
        return user
