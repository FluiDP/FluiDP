from django.urls import path
from . import views_colaborador as views

app_name = 'colaborador'

urlpatterns = [
     path('',
          views.colaborador_painel_view,
          name='home'),
     
     path('solicitacoes/',
          views.colaborador_solicitacoes_view,
          name='solicitacoes'),
     path('solicitacoes/criar/', 
          views.get_create_solicitacao_select_view,
          name='get_create_solicitacao_select'),
     path('solicitacoes/criar/<int:tipo_doc_id>/',
          views.get_create_solicitacao_form_view,
          name='get_create_solicitacao_form'),
     path('solicitacoes/salvar/<int:tipo_doc_id>/',
          views.salvar_solicitacao_view,
          name='salvar_solicitacao'),
     path('solicitacoes/detalhes/<int:solicitacao_id>/',
          views.get_solicitacao_detalhes_view, 
          name='get_solicitacao_detalhes'),
     path('solicitacoes/logs/<int:solicitacao_id>/', views.get_solicitacao_logs_view, name='solicitacao_logs'),
]
