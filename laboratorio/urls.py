from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_ordenes, name='lista_ordenes'),
    path('orden/nueva/', views.nueva_orden, name='nueva_orden'),
    path('orden/<int:orden_id>/', views.detalle_orden, name='detalle_orden'),
    path('orden/<int:orden_id>/pdf/', views.orden_pdf, name='orden_pdf'),
    path('orden/<int:orden_id>/resultados/', views.resultados_orden, name='resultados_orden'),

    # ➕ AJAX paciente
    path('paciente/nuevo/', views.paciente_nuevo_ajax, name='paciente_nuevo_ajax'),
    path('paciente/buscar/', views.buscar_paciente_ajax, name='buscar_paciente_ajax'),

    # ------------------------------
    # CATÁLOGO DE EXÁMENES
    # ------------------------------
    path('catalogo/', views.catalogo_examenes, name='catalogo_examenes'),
    path('catalogo/importar/', views.catalogo_importar_excel, name='catalogo_importar_excel'),
    path('catalogo/<int:examen_id>/editar/', views.catalogo_editar_ajax, name='catalogo_editar_ajax'),
    path('catalogo/<int:examen_id>/eliminar/', views.catalogo_eliminar_ajax, name='catalogo_eliminar_ajax'),


    path('buscar_examenes_ajax/', views.buscar_examenes_ajax, name='buscar_examenes_ajax'),

]
