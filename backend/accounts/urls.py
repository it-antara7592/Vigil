
from django.urls import path

from .views import (
    RegistrationView,
    LoginView,
    LogoutView,
    CurrentUserView,
    AccountDeletionView,
)


urlpatterns = [
    path('register/', RegistrationView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', CurrentUserView.as_view(), name='current-user'),
    path('deletion-request/', AccountDeletionView.as_view(), name='account-deletion'),
]
