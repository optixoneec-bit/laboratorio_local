from django.contrib import admin
from .models import Paciente, Examen, Orden, Muestra, OrdenExamen, Resultado, Equipo


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'documento_identidad', 'telefono', 'email')
    search_fields = ('nombre_completo', 'documento_identidad')


@admin.register(Examen)
class ExamenAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'area', 'precio', 'activo')
    search_fields = ('codigo', 'nombre', 'area')


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ('numero_orden', 'paciente', 'fecha', 'estado', 'total')
    search_fields = ('numero_orden', 'paciente__nombre_completo')


@admin.register(Muestra)
class MuestraAdmin(admin.ModelAdmin):
    list_display = ('codigo_barra', 'tipo', 'orden', 'hora_toma', 'etiqueta_impresa')
    search_fields = ('codigo_barra', 'orden__numero_orden')


@admin.register(OrdenExamen)
class OrdenExamenAdmin(admin.ModelAdmin):
    list_display = ('orden', 'examen', 'estado', 'precio')
    search_fields = ('orden__numero_orden', 'examen__nombre')


@admin.register(Resultado)
class ResultadoAdmin(admin.ModelAdmin):
    list_display = ('orden_examen', 'parametro', 'valor', 'unidad', 'validado')
    search_fields = ('parametro', 'orden_examen__orden__numero_orden')


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'modelo', 'protocolo', 'direccion_ip', 'puerto', 'estado_conexion')
    search_fields = ('nombre', 'modelo', 'direccion_ip')
