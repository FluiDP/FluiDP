from django.urls import path
from . import views_mobile as views

app_name = 'mobile'

urlpatterns = [
    path('', views.mobile_index_view, name='home'),
]
