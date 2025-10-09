from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_ordenes, name='lista_ordenes'),
    path('orden/nueva/', views.nueva_orden, name='nueva_orden'),
    path('orden/<int:orden_id>/', views.detalle_orden, name='detalle_orden'),
    path('orden/<int:orden_id>/pdf/', views.orden_pdf, name='orden_pdf'),
    path('orden/<int:orden_id>/resultados/', views.resultados_orden, name='resultados_orden'),
]
