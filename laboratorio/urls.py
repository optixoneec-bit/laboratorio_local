from django.urls import path
from . import views
from .views_informe import imprimir_informe   # ✅ IMPORTE CORRECTO Y FINAL


urlpatterns = [
    # -----------------------------
    # Órdenes
    # -----------------------------
    path('ordenes/', views.lista_ordenes, name='lista_ordenes'),
    path('ordenes/nueva/', views.nueva_orden, name='nueva_orden'),
    path('ordenes/<int:orden_id>/', views.detalle_orden, name='detalle_orden'),
    path('ordenes/<int:orden_id>/resultados/', views.resultados_orden, name='resultados_orden'),
    path('ordenes/<int:orden_id>/pdf/', views.orden_pdf, name='orden_pdf'),

    # ❌ SE ELIMINAN rutas incorrectas/duplicadas que NO existen en tu proyecto actual:
    # path('ordenes/<int:orden_id>/informe/', views.informe_resultados, ...)
    # path('ordenes/<int:orden_id>/informe/pdf/', views.informe_resultados_pdf, ...)
    # path("ordenes/<int:orden_id>/informe/pdf/", views.informe_resultados_pdf, ...)

    # -----------------------------
    # NUEVA RUTA OFICIAL PARA INFORME PDF
    # -----------------------------
    path("ordenes/<int:orden_id>/imprimir/", imprimir_informe, name="imprimir_informe"),

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
    # Buscador global
    # -----------------------------
    path('buscar_examenes/', views.buscar_examenes_ajax, name='buscar_examenes_ajax'),

    # -----------------------------
    # Resultados
    # -----------------------------
    path('resultado/<int:orden_examen_id>/registrar/', views.registrar_resultado, name='registrar_resultado'),
    path('resultado/<int:resultado_id>/validar/', views.validar_resultado, name='validar_resultado'),
    path('resultado/<int:resultado_id>/anular_validacion/', views.anular_validacion, name='anular_validacion'),
    path('resultado/burbuja/', views.burbuja_resultado_ajax, name='burbuja_resultado_ajax'),

    # -----------------------------
    # Módulo Resultados
    # -----------------------------
    path('resultados/', views.resultados_home, name='resultados_home'),
    path('resultados/<int:orden_id>/', views.resultados_orden, name='resultados_orden'),
    path('resultados/lista/', views.resultados_lista, name='resultados_lista'),
    path('guardar_resultados_ajax/', views.guardar_resultados_ajax, name='guardar_resultados_ajax'),

    # -----------------------------
    # Catálogo técnico
    # -----------------------------
    path('catalogo-tecnico/', views.catalogo_tecnico, name='catalogo_tecnico'),
    path('catalogo-tecnico/save', views.catalogo_tecnico_save, name='catalogo_tecnico_save'),
    path('catalogo-tecnico/create', views.catalogo_tecnico_create, name='catalogo_tecnico_create'),
    path('catalogo-tecnico/delete', views.catalogo_tecnico_delete, name='catalogo_tecnico_delete'),
    path('catalogo-tecnico/toggle-acreditado', views.catalogo_tecnico_toggle_acreditado, name='catalogo_tecnico_toggle_acreditado'),
    path('catalogo-tecnico/import', views.catalogo_tecnico_import, name='catalogo_tecnico_import'),
    path('catalogo-tecnico/export', views.catalogo_tecnico_export, name='catalogo_tecnico_export'),

    # -----------------------------
    # Validación
    # -----------------------------
    path('validacion/', views.validacion_lista, name='validacion_lista'),
    path('validacion/modal/<int:orden_id>/', views.validacion_modal_html, name='validacion_modal_html'),
    path('validacion/parametro/<int:resultado_id>/validar/', views.validar_parametro_ajax, name='validar_parametro_ajax'),
    path('validacion/parametro/<int:resultado_id>/anular/', views.anular_parametro_ajax, name='anular_parametro_ajax'),
    path('validacion/orden/<int:orden_id>/devolver/', views.devolver_a_resultados_ajax, name='devolver_a_resultados_ajax'),
    path('validacion/orden/<int:orden_id>/cerrar/', views.cerrar_validacion_orden_ajax, name='cerrar_validacion_orden_ajax'),

    # -----------------------------
    # Pacientes
    # -----------------------------
    path('pacientes/', views.pacientes_lista, name='pacientes_lista'),
    path('paciente/<int:paciente_id>/editar_ajax/', views.paciente_editar_ajax, name='paciente_editar_ajax'),
    path('paciente/<int:paciente_id>/actualizar_ajax/', views.paciente_actualizar_ajax, name='paciente_actualizar_ajax'),
    path('paciente/<int:paciente_id>/eliminar/', views.paciente_eliminar, name='paciente_eliminar'),


    path('ordenes/<int:orden_id>/etiquetas/pdf/', views.orden_etiquetas_pdf, name='orden_etiquetas_pdf'),



]
