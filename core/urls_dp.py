from django.urls import path
from . import views_dp as views

app_name = 'administracao'

urlpatterns = [
    path('', views.dp_dashboard_view, name='dashboard'),

    path('lotacoes', views.dp_lotacoes_view, name='lotacoes'),
    path('lotacoes/criar/', views.create_lotacao_modal_view, name='create_lotacao'),
    path('lotacoes/editar/<int:lotacao_id>/', views.edit_lotacao_modal_view, name='edit_lotacao'),
    path('lotacoes/arquivar/<int:pk>/', views.archive_lotacao_modal_view, name='archive_lotacao'),
    path('lotacoes/excluir/<int:pk>/', views.delete_lotacao_view, name='delete_lotacao'),

    path('cargos', views.dp_cargos_view, name='cargos'),
    path('cargos/criar/', views.create_cargo_modal_view, name='create_cargo'),
    path('cargos/editar/<int:pk>/', views.edit_cargo_modal_view, name='edit_cargo'),
    path('cargos/arquivar/<int:pk>/', views.archive_cargo_modal_view, name='archive_cargo'),
    path('cargos/excluir/<int:pk>/', views.delete_cargo_view, name='delete_cargo'),

    path('colaboradores', views.dp_colaboradores_view, name='colaboradores'),
    path('colaboradores/criar/', views.create_colaborador_modal_view, name='create_colaborador'),
    path('colaboradores/editar/<int:pk>/', views.edit_colaborador_modal_view, name='edit_colaborador'),
    path('colaboradores/arquivar/<int:pk>/', views.archive_colaborador_modal_view, name='archive_colaborador'),
    path('colaboradores/excluir/<int:pk>/', views.delete_colaborador_view, name='delete_colaborador'),

    path('documentos', views.dp_documentos_view, name='documentos'),
    path('documentos/criar/', views.create_documento_modal_view, name='create_documento'),
    path('documentos/editar/<int:pk>/', views.edit_documento_modal_view, name='edit_documento'),
    path('documentos/arquivar/<int:pk>/', views.archive_documento_modal_view, name='archive_documento'),
    path('documentos/excluir/<int:pk>/', views.delete_documento_view, name='delete_documento'),

    path('solicitacoes', views.dp_solicitacoes_view, name='solicitacoes'),
]
