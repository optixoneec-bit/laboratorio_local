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

    # ➕ Número de registro secuencial (empieza en 10001)
    numero_registro = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='paciente_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='paciente_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre_completo} ({self.documento_identidad})"

    def save(self, *args, **kwargs):
        # Asigna número consecutivo solo si no tiene
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
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    referencia_synlab = models.CharField(max_length=50, blank=True, null=True)
    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(User, related_name='examen_creado_por', on_delete=models.SET_NULL, null=True, blank=True)
    modificado_por = models.ForeignKey(User, related_name='examen_modificado_por', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Orden(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE)
    numero_orden = models.CharField(max_length=20, unique=True)
    fecha = models.DateTimeField(auto_now_add=True)
    medico = models.CharField(max_length=150, blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=[('Rutina', 'Rutina'), ('Urgente', 'Urgente')], default='Rutina')
    estado = models.CharField(max_length=20, choices=[
        ('Pendiente', 'Pendiente'),
        ('En proceso', 'En proceso'),
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
    orden_examen = models.ForeignKey(OrdenExamen, on_delete=models.CASCADE, related_name='resultados')
    parametro = models.CharField(max_length=100)
    valor = models.CharField(max_length=50)
    unidad = models.CharField(max_length=20, blank=True, null=True)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    validado = models.BooleanField(default=False)
    validado_por = models.ForeignKey(User, related_name='resultado_validado_por', on_delete=models.SET_NULL, null=True, blank=True)
    fecha_validacion = models.DateTimeField(null=True, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.parametro}: {self.valor}"


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
