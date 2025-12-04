from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('reset_password/', views.CustomPasswordResetView.as_view(), name='reset_password'),

    path('painel/', views.painel_view, name='painel'),
    path('perfil/', views.perfil_view, name='perfil'),

    path('administracao/', include('core.urls_dp')),
    path('colaborador/', include('core.urls_colaborador')),
    path('aprovador/', include('core.urls_aprovador')),
]
