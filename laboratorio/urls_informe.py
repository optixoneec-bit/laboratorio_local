from django.urls import path
from .views_informe import imprimir_informe

urlpatterns = [
    path('ordenes/<int:orden_id>/imprimir/', imprimir_informe, name='imprimir_informe'),
    path('ordenes/<int:orden_id>/pdf/', imprimir_informe, name='orden_pdf'),
]
