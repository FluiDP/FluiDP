from django.urls import path
from . import views_colaborador as views

app_name = 'colaborador'

urlpatterns = [
    path('', views.colaborador_painel_view, name='home'),
    path('solicitacoes/', views.colaborador_solicitacoes_view, name='solicitacoes'),
]
