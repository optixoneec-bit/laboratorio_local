from django.core.management.base import BaseCommand
from configuracion.models import HL7Mensaje
from configuracion.listener_thread import guardar_imagen_desde_obx


class Command(BaseCommand):
    help = "Regenera las imágenes PNG de mensajes HL7 antiguos."

    def handle(self, *args, **options):
        mensajes = HL7Mensaje.objects.filter(obx__icontains='|ED|').order_by('id')

        total_img = 0

        for msg in mensajes:
            print(f"Procesando mensaje {msg.id}...")

            # Borrar imágenes previas
            msg.imagenes.all().delete()

            for linea in msg.obx.split("\n"):
                if "|ED|" in linea:
                    guardar_imagen_desde_obx(msg, linea)
                    total_img += 1

        print(f"Listo. Imágenes generadas: {total_img}")
