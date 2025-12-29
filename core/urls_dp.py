from django.urls import path
from . import views_dp as views

app_name = 'administracao'

urlpatterns = [
    path('', views.dp_dashboard_view, name='dashboard'),

    path('lotacoes', views.dp_lotacoes_view, name='lotacoes'),
    path('lotacoes/criar/', views.create_lotacao_model_view, name='create_lotacao'),

    path('cargos', views.dp_cargos_view, name='cargos'),
    path('cargos/criar/', views.create_cargo_model_view, name='create_cargo'),

    path('colaboradores', views.dp_colaboradores_view, name='colaboradores'),

    path('documentos', views.dp_documentos_view, name='documentos'),

    path('solicitacoes', views.dp_solicitacoes_view, name='solicitacoes'),
]
