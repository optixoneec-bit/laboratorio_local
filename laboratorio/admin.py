from django.contrib import admin
from .models import Paciente, Examen, Orden, Muestra, OrdenExamen, PerfilUsuario


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('cedula', 'nombre_completo', 'sexo', 'fecha_nacimiento')
    search_fields = ('cedula', 'nombre_completo')


@admin.register(Examen)
class ExamenAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'area', 'precio_paciente', 'precio_pospago')
    search_fields = ('codigo', 'nombre')
    list_filter = ('area',)


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ('id', 'paciente', 'fecha_ingreso', 'estado', 'prioridad')
    list_filter = ('estado', 'prioridad')
    search_fields = ('paciente__nombre_completo', 'paciente__cedula')


@admin.register(Muestra)
class MuestraAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'tipo', 'orden', 'fecha_hora_toma')
    list_filter = ('tipo',)
    search_fields = ('codigo', 'orden__id')


@admin.register(OrdenExamen)
class OrdenExamenAdmin(admin.ModelAdmin):
    list_display = ('orden', 'examen', 'estado', 'fecha_validado')
    list_filter = ('estado', 'examen')
    search_fields = ('orden__id', 'examen__nombre')


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('user', 'rol')
    list_filter = ('rol',)
