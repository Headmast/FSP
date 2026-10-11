from django.urls import path
from . import views
urlpatterns = [path('me', views.me)]
urlpatterns += [
    path('catalog',views.catalog),path('me/profile',views.profile),path('me/profile/private',views.profile_private),
    path('me/profile/resume.pdf',views.profile_pdf),path('me/assessments',views.assessments),
    path('me/assessments/<str:pk>/result',views.assessment_result),path('me/achievements',views.achievements),
    path('invitations',views.invitations),path('invitations/<str:pk>',views.invitation),
    path('invitations/<str:pk>/contacts',views.invitation_contacts),
]
urlpatterns += [path('me/company',views.company),path('needs',views.needs),path('needs/<str:pk>',views.need),
    path('candidates',views.candidates),path('candidates/<str:pk>',views.candidate),
    path('candidates/<str:pk>/proofs',views.candidate_proofs),path('candidates/<str:pk>/private',views.candidate_private),
    path('candidates/<str:pk>/resume.pdf',views.candidate_pdf)]
urlpatterns += [path('openapi.json',views.openapi)]

urlpatterns += [path('',views.not_found),path('<path:unknown>',views.not_found)]
