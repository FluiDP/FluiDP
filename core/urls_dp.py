from django.urls import path
from . import views_dp as views

app_name = 'dp'

urlpatterns = [
    path('', views.dp_painel_view, name='home'),
]
