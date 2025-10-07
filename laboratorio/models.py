from django.db import models
from django.contrib.auth.models import User


class Paciente(models.Model):
    cedula = models.CharField(max_length=10, unique=True)
    nombre_completo = models.CharField(max_length=100)
    sexo = models.CharField(max_length=1, choices=[('M', 'Masculino'), ('F', 'Femenino')])
    fecha_nacimiento = models.DateField()
    correo = models.EmailField(blank=True, null=True)
    celular = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.nombre_completo} ({self.cedula})"

    def edad(self):
        from datetime import date
        return date.today().year - self.fecha_nacimiento.year


class Examen(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=100)
    area = models.CharField(max_length=50)
    precio_paciente = models.DecimalField(max_digits=6, decimal_places=2)
    precio_pospago = models.DecimalField(max_digits=6, decimal_places=2)
    unidad = models.CharField(max_length=20, blank=True)
    valores_referencia = models.TextField(blank=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Orden(models.Model):
    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('validada', 'Validada'),
        ('entregada', 'Entregada'),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE)
    fecha_ingreso = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    prioridad = models.CharField(max_length=10, choices=[('urgente', 'Urgente'), ('prioridad', 'Prioridad'), ('rutina', 'Rutina')], default='rutina')
    plan = models.CharField(max_length=100, blank=True, null=True)
    unidad = models.CharField(max_length=100, blank=True, null=True)
    nro_externo = models.CharField(max_length=20, blank=True, null=True)
    nota = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Orden {self.id} - {self.paciente.nombre_completo}"


class Muestra(models.Model):
    TIPO_MUESTRA = [
        ('suero', 'Suero'),
        ('sangre', 'Sangre Total con EDTA'),
        ('hisopado', 'Hisopado'),
        ('orina', 'Orina'),
        ('micologica', 'Muestras Micológicas'),
        ('otros', 'Otros'),
    ]

    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='muestras')
    tipo = models.CharField(max_length=30, choices=TIPO_MUESTRA)
    codigo = models.CharField(max_length=30, unique=True)
    fecha_hora_toma = models.DateTimeField()

    def __str__(self):
        return f"Muestra {self.codigo} ({self.tipo})"


class OrdenExamen(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='examenes')
    examen = models.ForeignKey(Examen, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20, choices=[('pendiente', 'Pendiente'), ('validado', 'Validado'), ('rev_web', 'Revisión Web')], default='pendiente')
    resultado = models.TextField(blank=True, null=True)
    fecha_validado = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.orden.id} - {self.examen.nombre}"


# Si deseas usar roles puedes definirlos así:
class PerfilUsuario(models.Model):
    ROLES = [
        ('recepcion', 'Recepción'),
        ('laboratorio', 'Laboratorio'),
        ('validador', 'Validador'),
        ('admin', 'Administrador'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=20, choices=ROLES)

    def __str__(self):
        return f"{self.user.username} - {self.rol}"
