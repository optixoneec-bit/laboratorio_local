from django.urls import path
from . import views

app_name = 'configuracion'

urlpatterns = [
    path('', views.dashboard_config, name='dashboard'),

    # Parámetros generales
    path('generales/', views.editar_generales, name='generales'),

    # Equipos e integración
    path('equipos/', views.equipos_lista, name='equipos_lista'),
    path('equipos/nuevo/', views.equipo_nuevo, name='equipo_nuevo'),
    path('equipos/<int:pk>/editar/', views.equipo_editar, name='equipo_editar'),
    path('equipos/<int:equipo_id>/mapeo/', views.equipo_mapeo_lista, name='equipo_mapeo_lista'),
    path('equipos/<int:equipo_id>/mapeo/nuevo/', views.equipo_mapeo_editar, name='equipo_mapeo_nuevo'),
    path('equipos/<int:equipo_id>/mapeo/<int:mapeo_id>/editar/', views.equipo_mapeo_editar, name='equipo_mapeo_editar'),

    # HL7 / LIS
    path('hl7/', views.hl7_dashboard, name='hl7_dashboard'),
    path('hl7/historial/', views.hl7_historial, name='hl7_historial'),
    path('hl7/<int:pk>/', views.hl7_ver, name='hl7_ver'),
    path('hl7/start/', views.hl7_start, name='hl7_start'),
    path('hl7/stop/', views.hl7_stop, name='hl7_stop'),

    # Roles y usuarios
    path('roles/', views.roles_dashboard, name='roles_dashboard'),
    path('roles/grupo/nuevo/', views.grupo_nuevo, name='grupo_nuevo'),
    path('roles/grupo/<int:pk>/editar/', views.grupo_editar, name='grupo_editar'),
    path('roles/grupo/<int:pk>/eliminar/', views.grupo_eliminar, name='grupo_eliminar'),
    path('roles/usuario/nuevo/', views.usuario_nuevo, name='usuario_nuevo'),
    path('roles/usuario/<int:user_id>/editar/', views.usuario_editar_roles, name='usuario_editar_roles'),
    path('roles/usuario/<int:user_id>/eliminar/', views.usuario_eliminar, name='usuario_eliminar'),
]
