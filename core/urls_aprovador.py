from django.urls import path
from . import views_aprovador as views

app_name = 'aprovador'

urlpatterns = [
    path('', views.aprovador_painel_view, name='home'),
]
