from django.urls import path
from . import views_mobile as views
from . import views_colaborador, views as views_gerais

app_name = 'mobile'

urlpatterns = [
    path('', views.mobile_index_view, name='home'),
    path('perfil/', views.mobile_perfil_view, name='perfil'),
    path('solicitacoes/detalhes/<int:solicitacao_id>/', views_colaborador.get_solicitacao_detalhes_view, name='get_solicitacao_detalhes'),
    path('solicitacoes/logs/<int:solicitacao_id>/', views_colaborador.get_solicitacao_logs_view, name='solicitacao_logs'),
    path('solicitacoes/pdf/<int:solicitacao_id>/', views_gerais.gerar_pdf_solicitacao_view, name='gerar_pdf_solicitacao'),
]
