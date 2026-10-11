from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from accounts import views as accounts
from accounts.forms import AccessibleAuthenticationForm

from accounts.integrations import integrations
from api.views import download_client
from profiles import views as profiles
from assessments import views as assessments
from hiring import views as hiring
from assistant import views as assistant
urlpatterns = [path("downloads/<str:filename>", download_client),
path("api/v1/", include("api.urls")),
path("accounts/integrations/", integrations, name="integrations"),
path("company/", hiring.company_profile, name="company-profile"),
    path("company/needs/", hiring.needs, name="needs"),
    path("candidates/", hiring.candidates, name="candidates"),
    path("candidates/<int:pk>/", hiring.candidate, name="candidate"),
    path("candidates/<int:pk>/resume.pdf", hiring.resume, name="candidate-resume"),
    path("invitations/", hiring.invitations, name="invitations"),
    path("invitations/send/", hiring.send, name="invitation-send"),
    path("invitations/<int:pk>/accept/", hiring.respond, {"status":"accepted"}, name="invitation-accept"),
    path("invitations/<int:pk>/decline/", hiring.respond, {"status":"declined"}, name="invitation-decline"),
    path("assistant/", assistant.assistant, name="assistant"),
    path("assistant/drafts/<int:pk>/", assistant.draft_detail, name="assistant-draft"),
    path("assessments/", assessments.dashboard, name="assessments"),
    path("assessments/start/", assessments.start, name="assessment-start"),
    path("assessments/<int:pk>/", assessments.attempt, name="attempt"),
    path("assessments/<int:pk>/proof/", assessments.proof, name="assessment-proof"),
    path("assessments/<int:pk>/answer/", assessments.answer, name="assessment-answer"),
    path("assessments/<int:pk>/finish/", assessments.finish, name="assessment-finish"),
    path("", accounts.home, name="home"),
    path("accounts/register/", accounts.register, name="register"),
    path("accounts/consent/", accounts.consent, name="consent"),
    path("accounts/privacy/", accounts.privacy, name="privacy"),
    path("accounts/login/", LoginView.as_view(template_name="accounts/login.html", authentication_form=AccessibleAuthenticationForm), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/confirm/", accounts.confirm, name="confirm"),
    path("profile/", profiles.profile, name="profile"),
    path("profile/resume.pdf", profiles.resume, name="resume"),
    path("profile/fsp/", profiles.fsp, name="fsp"),
    path("profile/fsp/link/", profiles.fsp_link, name="fsp-link"),
    path("health/", accounts.health, name="health"), path("version/", accounts.version, name="version")]
