from django.urls import path
from . import learning_views as views

urlpatterns = [
    path('', views.dashboard, name='learning'),
    path('lessons/<str:grade>/<slug:topic>/', views.lesson, name='learning-lesson'),
    path('lessons/<str:grade>/<slug:topic>/complete/', views.lesson_complete, name='learning-lesson-complete'),
    path('tracks/<slug:track>/lessons/<str:grade>/<slug:topic>/', views.lesson, name='learning-track-lesson'),
    path('tracks/<slug:track>/lessons/<str:grade>/<slug:topic>/complete/', views.lesson_complete, name='learning-track-lesson-complete'),
    path('start/', views.start, name='learning-start'),
    path('sessions/<int:pk>/', views.session, name='learning-session'),
    path('sessions/<int:pk>/answer/', views.answer, name='learning-answer'),
]
