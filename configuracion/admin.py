from django.contrib import admin
from .models import ConfigGeneral

@admin.register(ConfigGeneral)
class ConfigGeneralAdmin(admin.ModelAdmin):
    list_display = ('nombre_laboratorio', 'ruc', 'correo', 'iva_porcentaje', 'markup_por_defecto', 'actualizado')
