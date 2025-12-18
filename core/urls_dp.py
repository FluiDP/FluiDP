from django.urls import path
from . import views_dp as views

app_name = 'dp'

urlpatterns = [
    path('', views.dp_painel_view, name='home'),

    path('lotacoes', views.dp_lotacoes_view, name='lotacoes'),
    path('lotacoes/lista/', views.lotacoes_list_view, name='lotacoes_list'),
    path('lotacoes/criar/', views.create_lotacao_model_view, name='create_lotacao'),

    path('cargos', views.dp_cargos_view, name='cargos'),
    path('cargos/lista/', views.cargos_list_view, name='cargos_list'),
    path('cargos/criar/', views.create_cargo_model_view, name='create_cargo'),

    path('colaboradores', views.dp_colaboradores_view, name='colaboradores'),
    path('colaboradores/lista/', views.colaboradores_list_view, name='colaboradores_list'),

    path('documentos', views.dp_documentos_view, name='documentos'),
    path('documentos/lista/', views.documentos_list_view, name='documentos_list'),

    path('solicitacoes', views.dp_solicitacoes_view, name='solicitacoes'),
    path('solicitacoes/lista/', views.solicitacoes_list_view, name='solicitacoes_list'),
]
