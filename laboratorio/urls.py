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
    path('catalogo/exportar/', views.catalogo_exportar, name='catalogo_exportar'),

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




    path('guardar_resultados_ajax/', views.guardar_resultados_ajax, name='guardar_resultados_ajax'),

    # -----------------------------
    # Catalogo Tecnico
    # -----------------------------
    path('catalogo-tecnico/', views.catalogo_tecnico, name='catalogo_tecnico'),
    path('catalogo-tecnico/save', views.catalogo_tecnico_save, name='catalogo_tecnico_save'),
    path('catalogo-tecnico/create', views.catalogo_tecnico_create, name='catalogo_tecnico_create'),
    path('catalogo-tecnico/delete', views.catalogo_tecnico_delete, name='catalogo_tecnico_delete'),path('catalogo-tecnico/toggle-acreditado', views.catalogo_tecnico_toggle_acreditado, name='catalogo_tecnico_toggle_acreditado'),
    path('catalogo-tecnico/import', views.catalogo_tecnico_import, name='catalogo_tecnico_import'),
    path('catalogo-tecnico/export', views.catalogo_tecnico_export, name='catalogo_tecnico_export'),

]

