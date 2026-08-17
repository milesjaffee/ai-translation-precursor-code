from django.urls import path

from . import views

app_name = 'aligner'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('api/align/', views.AlignView.as_view(), name='align'),
]
