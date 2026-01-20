from django.urls import path
from . import views_gestor as views

app_name = 'gestor'

urlpatterns = [
     path('',
          views.aprovador_painel_view,
          name='home'),
     path('solicitacoes/aprovar/<int:solicitacao_id>/',
          views.aprovar_solicitacao_view,
          name='aprovar_solicitacao'),
     path('solicitacoes/recusar/<int:solicitacao_id>/',
          views.recusar_solicitacao_view,
          name='recusar_solicitacao'),
     path('dashboard/',
          views.gestor_dashboard_view,
          name='dashboard'),
]
