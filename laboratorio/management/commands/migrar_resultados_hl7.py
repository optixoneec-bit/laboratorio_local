"""
Comandos de gestión de Django para la migración de resultados HL7.
"""
from django.core.management.base import BaseCommand
from laboratorio.migrations_resultados import (
    migrar_resultados_desde_hl7, 
    reporte_migracion,
    procesar_mensajes_hl7_pendientes
)


class Command(BaseCommand):
    help = 'Migra resultados desde mensajes HL7 a la tabla Resultado'

    def add_arguments(self, parser):
        parser.add_argument(
            '--orden-id',
            type=int,
            help='ID específico de la orden a migrar (opcional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la migración sin guardar cambios',
        )
        parser.add_argument(
            '--reporte',
            action='store_true',
            help='Muestra un reporte de órdenes sin resultados',
        )
        parser.add_argument(
            '--procesar-pendientes',
            action='store_true',
            help='Procesa mensajes HL7 pendientes (estado=pendiente o sin_resultados)',
        )

    def handle(self, *args, **options):
        if options['reporte']:
            self.stdout.write(self.style.NOTICE('=== REPORTE DE MIGRACIÓN ==='))
            reporte = reporte_migracion()
            self.stdout.write(f'Órdenes sin resultados: {reporte["total_ordenes_sin_resultados"]}')
            
            if reporte['detalle']:
                self.stdout.write('')
                self.stdout.write('Detalle:')
                for item in reporte['detalle']:
                    self.stdout.write(
                        f'  - Orden: {item["numero_orden"]} | '
                        f'Paciente: {item["paciente"]} | '
                        f'HL7: {item["hl7_estado"]}'
                    )
            return

        if options['procesar_pendientes']:
            self.stdout.write(self.style.NOTICE('=== PROCESANDO MENSAJES HL7 PENDIENTES ==='))
            dry_run = options.get('dry_run', False)
            if dry_run:
                self.stdout.write(self.style.WARNING('MODO DRY-RUN: No se guardarán cambios'))
            
            resultados = procesar_mensajes_hl7_pendientes(dry_run=dry_run)
            
            self.stdout.write('')
            self.stdout.write(f'Mensajes procesados: {resultados["mensajes_procesados"]}')
            self.stdout.write(f'Mensajes sin orden: {resultados["mensajes_sin_orden"]}')
            self.stdout.write(f'Mensajes sin equipo: {resultados["mensajes_sin_equipo"]}')
            self.stdout.write(f'Mensajes sin mapeo: {resultados["mensajes_sin_mapeo"]}')
            self.stdout.write(f'Resultados creados: {resultados["resultados_creados"]}')
            self.stdout.write(f'Resultados ignorados: {resultados["resultados_ignorados"]}')

            if resultados['errores']:
                self.stdout.write('')
                self.stdout.write(self.style.ERROR('Errores:'))
                for error in resultados['errores']:
                    self.stdout.write(f'  - {error}')
            return

        orden_id = options.get('orden_id')
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN: No se guardarán cambios'))

        self.stdout.write(self.style.NOTICE('=== INICIANDO MIGRACIÓN ==='))

        resultados = migrar_resultados_desde_hl7(orden_id=orden_id, dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write(f'Órdenes procesadas: {resultados["ordenes_procesadas"]}')
        self.stdout.write(f'Órdenes sin mensaje HL7: {resultados["ordenes_sin_mensaje"]}')
        self.stdout.write(f'Órdenes sin mapeo: {resultados["ordenes_sin_mapeo"]}')
        self.stdout.write(f'Resultados creados: {resultados["resultados_creados"]}')
        self.stdout.write(f'Resultados ignorados: {resultados["resultados_ignorados"]}')

        if resultados['errores']:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR('Errores:'))
            for error in resultados['errores']:
                self.stdout.write(f'  - {error}')
