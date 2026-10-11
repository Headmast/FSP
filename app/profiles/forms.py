import re
from django import forms
from .models import Profile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("name", "city", "skills", "contact_email", "contact_phone", "desired_grade", "published")
        labels = {"name": "Имя", "city": "Город", "skills": "Навыки через запятую", "contact_email": "Контактный email (скрыт)",
                  "contact_phone": "Телефон (скрыт)", "desired_grade": "Категория для теста", "published": "Разрешаю публикацию профиля"}
    def clean_skills(self):
        skills = self.cleaned_data["skills"]
        allowed = {"swift", "swiftui", "uikit", "combine", "coredata", "core data", "git", "xctest", "urlsession"}
        if any(skill.strip().lower() not in allowed for skill in skills.split(",") if skill.strip()):
            raise forms.ValidationError("Допустимые навыки: Swift, SwiftUI, UIKit, Combine, CoreData, Git, XCTest, URLSession.")
        return skills

    def public_name(self, value):
        if value and not re.fullmatch(r"[^\W\d_]+(?:[ -][^\W\d_]+)*", value, flags=re.UNICODE):
            raise forms.ValidationError("Только имя или город: буквы, пробел и дефис. Контакты укажите в скрытых полях.")
        return value

    def clean_name(self):
        return self.public_name(self.cleaned_data["name"].strip())

    def clean_city(self):
        return self.public_name(self.cleaned_data["city"].strip())

    def clean(self):
        data = super().clean()
        if data.get("published") and not data.get("name"):
            raise forms.ValidationError("Для публикации заполните имя.")
        return data
