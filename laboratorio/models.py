from django.db import models
from django.contrib.auth.models import User
from django.db.models import Max


class Paciente(models.Model):
    documento_identidad = models.CharField(max_length=20, unique=True)
    nombre_completo = models.CharField(max_length=150)
    sexo = models.CharField(max_length=10, choices=[('M', 'Masculino'), ('F', 'Femenino')])
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)

    numero_registro = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='paciente_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='paciente_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre_completo} ({self.documento_identidad})"

    def save(self, *args, **kwargs):
        if self.numero_registro is None:
            max_val = Paciente.objects.aggregate(m=Max('numero_registro'))['m'] or 10000
            self.numero_registro = max_val + 1
        super().save(*args, **kwargs)


class Equipo(models.Model):
    nombre = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100, blank=True, null=True)
    protocolo = models.CharField(max_length=50, choices=[
        ('HL7', 'HL7'),
        ('ASTM', 'ASTM'),
        ('TXT', 'Archivo TXT'),
        ('CSV', 'Archivo CSV'),
    ], default='HL7')
    direccion_ip = models.GenericIPAddressField(blank=True, null=True)
    puerto = models.IntegerField(default=5000)
    estado_conexion = models.BooleanField(default=False)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='equipo_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='equipo_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} ({self.modelo})"


class Examen(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=200)
    area = models.CharField(max_length=100)
    unidad = models.CharField(max_length=50, blank=True, null=True)
    muestra = models.CharField(max_length=100, blank=True, null=True)  # 🧪 NUEVO CAMPO
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    referencia_synlab = models.CharField(max_length=50, blank=True, null=True)
    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='examen_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='examen_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class ExamenParametro(models.Model):
    examen = models.ForeignKey('Examen', on_delete=models.CASCADE, related_name='parametros')
    nombre = models.CharField(max_length=120, verbose_name="Nombre del parámetro")
    unidad = models.CharField(max_length=50, blank=True, null=True, verbose_name="Unidad")
    referencia = models.CharField(max_length=100, blank=True, null=True, verbose_name="Valores de referencia")
    metodo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Método analítico")
    observacion = models.TextField(blank=True, null=True, verbose_name="Observaciones automáticas")
    acreditado = models.BooleanField(default=True, verbose_name="Acreditado")

    class Meta:
        ordering = ['examen', 'nombre']
        verbose_name = "Parámetro de examen"
        verbose_name_plural = "Parámetros de examen"

    def __str__(self):
        return f"{self.examen.nombre} - {self.nombre}"


class Orden(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE)
    numero_orden = models.CharField(max_length=20, unique=True)
    fecha = models.DateTimeField(auto_now_add=True)
    medico = models.CharField(max_length=150, blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=[('Rutina', 'Rutina'), ('Urgente', 'Urgente')], default='Rutina')
    estado = models.CharField(max_length=20, choices=[
         ('Pendiente', 'Pendiente'),
        ('En proceso', 'En proceso'),
        ('En validación', 'En validación'),
        ('Validado', 'Validado'),
    ], default='Pendiente')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    observaciones = models.TextField(blank=True, null=True)
    equipo = models.ForeignKey(Equipo, on_delete=models.SET_NULL, null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='orden_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='orden_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Orden {self.numero_orden} - {self.paciente.nombre_completo}"


class OrdenExamen(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='examenes')
    examen = models.ForeignKey(Examen, on_delete=models.CASCADE)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    estado = models.CharField(max_length=20, choices=[
        ('Pendiente', 'Pendiente'),
        ('Procesado', 'Procesado'),
        ('Validado', 'Validado'),
    ], default='Pendiente')

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='ordenexamen_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='ordenexamen_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.orden.numero_orden} - {self.examen.nombre}"


class Resultado(models.Model):
    orden_examen = models.ForeignKey('OrdenExamen', on_delete=models.CASCADE, related_name='resultados')
    parametro = models.CharField(max_length=120, verbose_name="Parámetro")
    valor = models.CharField(max_length=50, blank=True, null=True, verbose_name="Valor")
    unidad = models.CharField(max_length=50, blank=True, null=True, verbose_name="Unidad")
    referencia = models.CharField(max_length=100, blank=True, null=True, verbose_name="Valores de referencia")
    observacion = models.TextField(blank=True, null=True, verbose_name="Observaciones")
    metodo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Método")
    acreditado = models.BooleanField(default=True, verbose_name="Acreditado")
    fuera_de_rango = models.BooleanField(default=False, verbose_name="Fuera de rango")
    es_calculado = models.BooleanField(default=False, verbose_name="Es calculado")
    validado = models.BooleanField(default=False, verbose_name="Validado")
    validado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='resultados_validados')
    fecha_validacion = models.DateTimeField(blank=True, null=True)
    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)
    verificado = models.BooleanField(default=False)


    class Meta:
        ordering = ['orden_examen', 'parametro']

    def __str__(self):
        return f"{self.parametro} ({self.valor or ''})"

    def marca_fuera_de_rango(self):
        """
        Determina automáticamente si el valor está fuera del rango de referencia.
        """
        try:
            if not self.referencia or not self.valor:
                return
            ref = self.referencia.replace(',', '.')
            if '-' in ref:
                min_val, max_val = [float(x.strip()) for x in ref.split('-')]
                val = float(self.valor.replace(',', '.'))
                self.fuera_de_rango = not (min_val <= val <= max_val)
        except Exception:
            self.fuera_de_rango = False



class Muestra(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='muestras')
    codigo_barra = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=100, choices=[
        ('Sangre', 'Sangre'),
        ('Orina', 'Orina'),
        ('Heces', 'Heces'),
        ('Otro', 'Otro'),
    ], default='Sangre')
    hora_toma = models.DateTimeField(auto_now_add=True)
    etiqueta_impresa = models.BooleanField(default=False)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='muestra_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='muestra_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Muestra {self.codigo_barra} ({self.tipo})"
