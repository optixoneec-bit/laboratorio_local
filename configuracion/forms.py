from django import forms
from .models import ConfigGeneral, Equipo, EquipoMapeo


class ConfigGeneralForm(forms.ModelForm):
    class Meta:
        model = ConfigGeneral
        fields = [
            'nombre_laboratorio', 'ruc', 'direccion', 'telefono', 'correo',
            'logo', 'iva_porcentaje', 'markup_por_defecto'
        ]
        widgets = {
            'nombre_laboratorio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del laboratorio'}),
            'ruc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RUC / Identificación'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dirección'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono(s)'}),
            'correo': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Correo de contacto'}),
            'iva_porcentaje': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'markup_por_defecto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = [
            'nombre', 'codigo', 'fabricante', 'modelo',
            'tipo_integracion', 'host', 'puerto',
            'ruta_archivos', 'prefijo_archivo',
            'activo', 'notas'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'fabricante': forms.TextInput(attrs={'class': 'form-control'}),
            'modelo': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_integracion': forms.Select(attrs={'class': 'form-control'}),
            'host': forms.TextInput(attrs={'class': 'form-control'}),
            'puerto': forms.TextInput(attrs={'class': 'form-control'}),
            'ruta_archivos': forms.TextInput(attrs={'class': 'form-control'}),
            'prefijo_archivo': forms.TextInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class EquipoMapeoForm(forms.ModelForm):
    class Meta:
        model = EquipoMapeo
        fields = ['codigo_equipo', 'examen', 'parametro', 'activo']
        widgets = {
            'codigo_equipo': forms.TextInput(attrs={'class': 'form-control'}),
            'examen': forms.Select(attrs={'class': 'form-control'}),
            'parametro': forms.TextInput(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
