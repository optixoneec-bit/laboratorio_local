# laboratorio/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # -----------------------------
    # Órdenes
    # -----------------------------
    path('ordenes/', views.lista_ordenes, name='lista_ordenes'),
    path('ordenes/nueva/', views.nueva_orden, name='nueva_orden'),
    path('ordenes/<int:orden_id>/', views.detalle_orden, name='detalle_orden'),
    path('ordenes/<int:orden_id>/resultados/', views.resultados_orden, name='resultados_orden'),
    path('ordenes/<int:orden_id>/pdf/', views.orden_pdf, name='orden_pdf'),

    # -----------------------------
    # Pacientes (AJAX)
    # -----------------------------
    path('paciente/nuevo/', views.paciente_nuevo_ajax, name='paciente_nuevo_ajax'),
    path('paciente/buscar/', views.buscar_paciente_ajax, name='buscar_paciente_ajax'),

    # -----------------------------
    # Catálogo
    # -----------------------------
    path('catalogo/', views.catalogo_examenes, name='catalogo_examenes'),
    path('catalogo/importar/', views.catalogo_importar_excel, name='catalogo_importar_excel'),
    path('catalogo/<int:examen_id>/editar/', views.catalogo_editar_ajax, name='catalogo_editar_ajax'),
    path('catalogo/<int:examen_id>/eliminar/', views.catalogo_eliminar_ajax, name='catalogo_eliminar_ajax'),
    path('catalogo/eliminar_todos/', views.catalogo_eliminar_todos_ajax, name='catalogo_eliminar_todos_ajax'),

    # -----------------------------
    # Buscador global de exámenes (AJAX)
    # -----------------------------
    path('buscar_examenes/', views.buscar_examenes_ajax, name='buscar_examenes_ajax'),

    # -----------------------------
    # Resultados
    # -----------------------------
    path('resultado/<int:orden_examen_id>/registrar/', views.registrar_resultado, name='registrar_resultado'),
    path('resultado/<int:resultado_id>/validar/', views.validar_resultado, name='validar_resultado'),
    path('resultado/<int:resultado_id>/anular_validacion/', views.anular_validacion, name='anular_validacion'),

    # -----------------------------
    # Módulo Resultados (inicio)
    # -----------------------------
    path('resultados/', views.resultados_home, name='resultados_home'),
    path('resultados/<int:orden_id>/', views.resultados_orden, name='resultados_orden'),

    # -----------------------------
    # Nueva vista principal para carga de resultados (AGREGADA)
    # -----------------------------
    path('resultados/lista/', views.resultados_lista, name='resultados_lista'),
]
