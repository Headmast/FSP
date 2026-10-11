from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from accounts import views as accounts
from profiles import views as profiles
urlpatterns = [path("", accounts.home, name="home"),
    path("accounts/register/", accounts.register, name="register"),
    path("accounts/login/", LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/confirm/", accounts.confirm, name="confirm"),
    path("profile/", profiles.profile, name="profile"),
    path("profile/resume.pdf", profiles.resume, name="resume"),
    path("profile/fsp/", profiles.fsp, name="fsp"),
    path("health/", accounts.health, name="health"), path("version/", accounts.version, name="version")]
