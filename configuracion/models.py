from django.db import models
from laboratorio.models import Examen


class ConfigGeneral(models.Model):
    nombre_laboratorio = models.CharField(max_length=180, default='Mi Laboratorio')
    ruc = models.CharField(max_length=20, blank=True, default='')
    direccion = models.CharField(max_length=250, blank=True, default='')
    telefono = models.CharField(max_length=120, blank=True, default='')
    correo = models.EmailField(blank=True, default='')
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=12.00)
    markup_por_defecto = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    actualizado = models.DateTimeField(auto_now=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Parámetro general'
        verbose_name_plural = 'Parámetros generales'

    def __str__(self):
        return f'Configuración: {self.nombre_laboratorio}'

    @classmethod
    def unica(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Equipo(models.Model):
    TIPO_INTEGRACION_CHOICES = [
        ('MANUAL', 'Sin integración (solo manual)'),
        ('ASTM', 'ASTM (Puerto serie)'),
        ('HL7', 'HL7 (TCP/IP)'),
        ('CSV', 'Archivo CSV'),
        ('TXT', 'Archivo TXT'),
    ]

    nombre = models.CharField(max_length=160)
    codigo = models.CharField(max_length=50, unique=True)
    fabricante = models.CharField(max_length=120, blank=True, default='')
    modelo = models.CharField(max_length=120, blank=True, default='')
    tipo_integracion = models.CharField(
        max_length=10,
        choices=TIPO_INTEGRACION_CHOICES,
        default='MANUAL'
    )
    host = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text='IP o nombre de host (solo para HL7/ASTM TCP).'
    )
    puerto = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='Puerto TCP o COM (según el tipo de integración).'
    )
    ruta_archivos = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Ruta de carpeta para archivos CSV/TXT.'
    )
    prefijo_archivo = models.CharField(
        max_length=60,
        blank=True,
        default='',
        help_text='Prefijo de nombre de archivo que el LIS debe leer (opcional).'
    )
    activo = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default='')
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'

    def __str__(self):
        return f'{self.nombre} ({self.codigo})'


class EquipoMapeo(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='mapeos')
    codigo_equipo = models.CharField(
        max_length=80,
        help_text='Código que envía el equipo en el mensaje/archivo.'
    )
    examen = models.ForeignKey(
        Examen,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Examen interno al que se asignará.'
    )
    parametro = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text='Parámetro interno (ej. GLUCOSA, HGB, PCR-US).'
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Mapeo de equipo'
        verbose_name_plural = 'Mapeos de equipos'
        unique_together = ('equipo', 'codigo_equipo')

    def __str__(self):
        return f'{self.equipo.codigo} -> {self.codigo_equipo}'

class HL7Mensaje(models.Model):
    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    ip_equipo = models.CharField(max_length=100, blank=True, null=True)
    mensaje_raw = models.TextField()

    msh = models.TextField(blank=True, null=True)
    pid = models.TextField(blank=True, null=True)
    obr = models.TextField(blank=True, null=True)
    obx = models.TextField(blank=True, null=True)

    sample_id = models.CharField(max_length=100, blank=True, null=True)
    exam_codes = models.CharField(max_length=500, blank=True, null=True)

    estado = models.CharField(max_length=20, default="pendiente")

    def __str__(self):
        return f"Mensaje HL7 {self.id} - {self.fecha_recepcion}"
    
class HL7Imagen(models.Model):
    mensaje = models.ForeignKey(HL7Mensaje, on_delete=models.CASCADE, related_name="imagenes")
    archivo = models.ImageField(upload_to="lis_imagenes/%Y/%m/%d/")
    tipo = models.CharField(max_length=50, blank=True, null=True)  # ej: 'DIFF', 'SCATTER'
    formato = models.CharField(max_length=20, default="bmp")
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Imagen {self.id} del mensaje {self.mensaje_id}"
