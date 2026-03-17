"""
Funciones para migrar resultados desde mensajes HL7 antiguos a la tabla Resultado.
Esto permite que el generador de PDF con gráficas pueda mostrar resultados de órdenes antiguas.
"""
from django.db import transaction
from django.db.models import Q

from configuracion.models import HL7Mensaje, Equipo, EquipoMapeo
from laboratorio.models import Orden, OrdenExamen, Resultado


def _parse_msh_fields(msh_line: str):
    """Parse MSH segment to extract sending app and facility."""
    out = {"sending_app": "", "sending_facility": ""}
    try:
        if not msh_line:
            return out
        parts = msh_line.split("|")
        out["sending_app"] = (parts[2] or "").strip() if len(parts) > 2 else ""
        out["sending_facility"] = (parts[3] or "").strip() if len(parts) > 3 else ""
    except Exception:
        pass
    return out


def _extract_obx_items(hl7_raw_text: str):
    """
    Extrae items OBX del mensaje HL7.
    Devuelve lista de diccionarios con: seq, code, value, unit, ref, type, raw_obx3
    """
    items = []

    try:
        for line in (hl7_raw_text or "").split("\r"):
            line = (line or "").strip()
            if not line.startswith("OBX|"):
                continue

            parts = line.split("|")
            if len(parts) < 6:
                continue

            try:
                seq = int(parts[1])
            except Exception:
                seq = 0

            vtype = (parts[2] or "").strip()
            obx3 = (parts[3] or "").strip()
            val = (parts[5] or "").strip()
            unit = (parts[6] or "").strip() if len(parts) > 6 else ""
            ref = (parts[7] or "").strip() if len(parts) > 7 else ""

            parts3 = obx3.split("^")
            code = parts3[1].strip() if len(parts3) > 1 else ""

            if not code:
                continue

            items.append({
                "seq": seq,
                "code": code,
                "raw_obx3": obx3,
                "value": val,
                "unit": unit,
                "ref": ref,
                "type": vtype,
            })

    except Exception:
        pass

    return items


def _is_graph_or_binary_obx(item):
    """
    Determina si un OBX es de gráfica/binario (se debe ignorar).
    """
    try:
        if (item.get("type") or "").upper() == "ED":
            return True
        raw_obx3 = (item.get("raw_obx3") or "")
        code = (item.get("code") or "")

        txt = f"{raw_obx3} {code}"
        if "Histogram" in txt or "Scatter" in txt or ".Binary" in txt:
            return True
    except Exception:
        return True
    return False


def _detectar_equipo_desde_mensaje(msg: HL7Mensaje):
    """
    Detecta el equipo que envió el mensaje HL7.
    """
    # Primero intentar por IP
    if msg.ip_equipo:
        eq = Equipo.objects.filter(
            activo=True, 
            host=str(msg.ip_equipo).strip()
        ).order_by("id").first()
        if eq:
            return eq

    # Luego por MSH
    try:
        msh_line = msg.msh or ""
        msh = _parse_msh_fields(msh_line)
        app = msh.get("sending_app", "")
        fac = msh.get("sending_facility", "")

        qs = Equipo.objects.filter(activo=True)

        if fac:
            qs = qs.filter(
                Q(codigo__icontains=fac) |
                Q(modelo__icontains=fac) |
                Q(nombre__icontains=fac)
            )
        if app:
            qs = qs.filter(
                Q(codigo__icontains=app) |
                Q(fabricante__icontains=app) |
                Q(nombre__icontains=app)
            )
        return qs.order_by("id").first()
    except Exception:
        return None


def migrar_resultados_desde_hl7(orden_id=None, dry_run=False):
    """
    Migra los resultados desde mensajes HL7 a la tabla Resultado.
    
    Args:
        orden_id: Si se especifica, solo procesa esta orden. Si es None, procesa todas las órdenes sin resultados.
        dry_run: Si es True, no guarda nada, solo retorna lo que se procesaría.
    
    Returns:
        Diccionario con estadísticas de la migración.
    """
    resultados = {
        "ordenes_procesadas": 0,
        "ordenes_sin_mensaje": 0,
        "ordenes_sin_mapeo": 0,
        "resultados_creados": 0,
        "resultados_ignorados": 0,
        "errores": [],
        "detalle": []
    }

    # Obtener órdenes a procesar
    if orden_id:
        ordenes = Orden.objects.filter(id=orden_id)
    else:
        # Órdenes que NO tienen resultados en la tabla Resultado
        ordenes = Orden.objects.filter(
            examenes__resultados__isnull=True
        ).distinct()

    for orden in ordenes:
        num_orden = orden.numero_orden
        
        # Buscar mensaje HL7 que coincida con el número de orden
        msg = HL7Mensaje.objects.filter(
            sample_id=num_orden
        ).first()

        if not msg:
            resultados["ordenes_sin_mensaje"] += 1
            resultados["detalle"].append({
                "orden": num_orden,
                "estado": "sin_mensaje_hl7",
                "mensaje": f"No se encontró mensaje HL7 para sample_id: {num_orden}"
            })
            continue

        # Detectar equipo
        equipo = _detectar_equipo_desde_mensaje(msg)
        if not equipo:
            resultados["detalle"].append({
                "orden": num_orden,
                "estado": "sin_equipo",
                "mensaje": "No se pudo detectar el equipo del mensaje"
            })
            continue

        # Obtener mapeos
        mapeos = EquipoMapeo.objects.filter(
            equipo=equipo, 
            activo=True
        ).select_related("examen").all()
        
        mapa = {}
        for mp in mapeos:
            if mp.codigo_equipo:
                mapa[mp.codigo_equipo.strip()] = mp

        if not mapa:
            resultados["ordenes_sin_mapeo"] += 1
            resultados["detalle"].append({
                "orden": num_orden,
                "estado": "sin_mapeos",
                "mensaje": f"El equipo {equipo.codigo} no tiene mapeos configurados"
            })
            continue

        # Extraer OBX
        items = _extract_obx_items(msg.mensaje_raw or "")
        if not items:
            resultados["detalle"].append({
                "orden": num_orden,
                "estado": "sin_obx",
                "mensaje": "El mensaje HL7 no contiene segmentos OBX"
            })
            continue

        resultados["ordenes_procesadas"] += 1

        if dry_run:
            resultados["detalle"].append({
                "orden": num_orden,
                "estado": "dry_run",
                "mensaje": f"Se procesarían {len(items)} OBX"
            })
            continue

        # Procesar resultados
        with transaction.atomic():
            for it in items:
                # Ignorar gráficas/binarios
                if _is_graph_or_binary_obx(it):
                    resultados["resultados_ignorados"] += 1
                    continue

                code = (it.get("code") or "").strip()
                if not code:
                    resultados["resultados_ignorados"] += 1
                    continue

                mp = mapa.get(code)
                if not mp or not mp.examen:
                    resultados["resultados_ignorados"] += 1
                    continue

                param = (mp.parametro or "").strip()
                if not param:
                    resultados["resultados_ignorados"] += 1
                    continue

                # Buscar OrdenExamen
                oe = OrdenExamen.objects.filter(
                    orden=orden, 
                    examen=mp.examen
                ).first()
                
                if not oe:
                    resultados["resultados_ignorados"] += 1
                    continue

                # Crear o actualizar resultado
                valor = it.get("value")
                if valor and valor.strip() != "":
                    valor = valor.strip()
                else:
                    valor = None

                unidad = it.get("unit")
                if unidad and unidad.strip() != "":
                    unidad = unidad.strip()
                else:
                    unidad = None

                referencia = it.get("ref")
                if referencia and referencia.strip() != "":
                    referencia = referencia.strip()
                else:
                    referencia = None

                obj, created = Resultado.objects.update_or_create(
                    orden_examen=oe,
                    parametro=param,
                    defaults={
                        "valor": valor,
                        "unidad": unidad,
                        "referencia": referencia,
                        "orden_equipo": int(it.get("seq") or 0),
                    }
                )

                # Calcular fuera de rango
                try:
                    if hasattr(obj, "marca_fuera_de_rango"):
                        obj.marca_fuera_de_rango()
                        obj.save(update_fields=["fuera_de_rango"])
                except Exception:
                    pass

                if created:
                    resultados["resultados_creados"] += 1

            # Actualizar estado de la orden
            try:
                if orden.estado == "Pendiente":
                    orden.estado = "En validación"
                    orden.save(update_fields=["estado"])
            except Exception as e:
                resultados["errores"].append(f"Error actualizando estado de orden {num_orden}: {str(e)}")

            # Actualizar estado de OrdenExamen
            try:
                OrdenExamen.objects.filter(orden=orden).exclude(estado="Validado").update(estado="Procesado")
            except Exception as e:
                resultados["errores"].append(f"Error actualizando estado de OrdenExamen: {str(e)}")

            # Marcar mensaje como procesado
            try:
                if msg.estado == "pendiente":
                    msg.estado = "procesado"
                    msg.save(update_fields=["estado"])
            except Exception:
                pass

        resultados["detalle"].append({
            "orden": num_orden,
            "estado": "ok",
            "mensaje": f"Procesado con {resultados['resultados_creados']} resultados"
        })

    return resultados


def reporte_migracion():
    """
    Genera un reporte de cuántas órdenes necesitan ser migradas.
    """
    # Órdenes sin resultados
    ordenes_sin_resultados = Orden.objects.filter(
        examenes__resultados__isnull=True
    ).distinct()

    reporte = {
        "total_ordenes_sin_resultados": ordenes_sin_resultados.count(),
        "detalle": []
    }

    for orden in ordenes_sin_resultados:
        num_orden = orden.numero_orden
        
        # Verificar si existe mensaje HL7
        msg = HL7Mensaje.objects.filter(sample_id=num_orden).first()
        
        if msg:
            # Verificar si ya está procesado
            estado = "ok" if msg.estado == "procesado" else msg.estado
        else:
            estado = "sin_mensaje"

        reporte["detalle"].append({
            "orden_id": orden.id,
            "numero_orden": num_orden,
            "paciente": orden.paciente.nombre_completo,
            "fecha": orden.fecha.strftime("%Y-%m-%d %H:%M") if orden.fecha else None,
            "hl7_estado": estado
        })

    return reporte


def procesar_mensajes_hl7_pendientes(dry_run=False):
    """
    Procesa todos los mensajes HL7 que están en estado 'pendiente' o 'sin_resultados'.
    Esto es útil para migrar datos antiguos que no fueron procesados automáticamente.
    
    Args:
        dry_run: Si es True, no guarda nada, solo retorna lo que se procesaría.
    
    Returns:
        Diccionario con estadísticas del procesamiento.
    """
    resultados = {
        "mensajes_procesados": 0,
        "mensajes_sin_orden": 0,
        "mensajes_sin_equipo": 0,
        "mensajes_sin_mapeo": 0,
        "resultados_creados": 0,
        "resultados_ignorados": 0,
        "errores": [],
        "detalle": []
    }

    # Buscar mensajes que no están procesados
    mensajes = HL7Mensaje.objects.filter(
        Q(estado='pendiente') | Q(estado='sin_resultados')
    ).order_by('id')

    for msg in mensajes:
        num_orden = msg.sample_id
        
        # Buscar orden que coincida con el sample_id
        orden = Orden.objects.filter(numero_orden=num_orden).first()
        
        if not orden:
            resultados["mensajes_sin_orden"] += 1
            resultados["detalle"].append({
                "mensaje_id": msg.id,
                "sample_id": num_orden,
                "estado": "sin_orden",
                "mensaje": f"No existe orden para sample_id: {num_orden}"
            })
            continue

        # Detectar equipo
        equipo = _detectar_equipo_desde_mensaje(msg)
        if not equipo:
            resultados["mensajes_sin_equipo"] += 1
            resultados["detalle"].append({
                "mensaje_id": msg.id,
                "sample_id": num_orden,
                "estado": "sin_equipo",
                "mensaje": "No se pudo detectar el equipo del mensaje"
            })
            continue

        # Obtener mapeos
        mapeos = EquipoMapeo.objects.filter(
            equipo=equipo, 
            activo=True
        ).select_related("examen").all()
        
        mapa = {}
        for mp in mapeos:
            if mp.codigo_equipo:
                mapa[mp.codigo_equipo.strip()] = mp

        if not mapa:
            resultados["mensajes_sin_mapeo"] += 1
            resultados["detalle"].append({
                "mensaje_id": msg.id,
                "sample_id": num_orden,
                "estado": "sin_mapeo",
                "mensaje": f"El equipo {equipo.codigo} no tiene mapeos configurados"
            })
            continue

        # Extraer OBX
        items = _extract_obx_items(msg.mensaje_raw or "")
        if not items:
            resultados["detalle"].append({
                "mensaje_id": msg.id,
                "sample_id": num_orden,
                "estado": "sin_obx",
                "mensaje": "El mensaje HL7 no contiene segmentos OBX"
            })
            continue

        resultados["mensajes_procesados"] += 1

        if dry_run:
            resultados["detalle"].append({
                "mensaje_id": msg.id,
                "sample_id": num_orden,
                "estado": "dry_run",
                "mensaje": f"Se procesarían {len(items)} OBX para orden {num_orden}"
            })
            continue

        # Procesar resultados
        with transaction.atomic():
            for it in items:
                # Ignorar gráficas/binarios
                if _is_graph_or_binary_obx(it):
                    resultados["resultados_ignorados"] += 1
                    continue

                code = (it.get("code") or "").strip()
                if not code:
                    resultados["resultados_ignorados"] += 1
                    continue

                mp = mapa.get(code)
                if not mp or not mp.examen:
                    resultados["resultados_ignorados"] += 1
                    continue

                param = (mp.parametro or "").strip()
                if not param:
                    resultados["resultados_ignorados"] += 1
                    continue

                # Buscar OrdenExamen
                oe = OrdenExamen.objects.filter(
                    orden=orden, 
                    examen=mp.examen
                ).first()
                
                if not oe:
                    resultados["resultados_ignorados"] += 1
                    continue

                # Crear o actualizar resultado
                valor = it.get("value")
                if valor and valor.strip() != "":
                    valor = valor.strip()
                else:
                    valor = None

                unidad = it.get("unit")
                if unidad and unidad.strip() != "":
                    unidad = unidad.strip()
                else:
                    unidad = None

                referencia = it.get("ref")
                if referencia and referencia.strip() != "":
                    referencia = referencia.strip()
                else:
                    referencia = None

                obj, created = Resultado.objects.update_or_create(
                    orden_examen=oe,
                    parametro=param,
                    defaults={
                        "valor": valor,
                        "unidad": unidad,
                        "referencia": referencia,
                        "orden_equipo": int(it.get("seq") or 0),
                    }
                )

                # Calcular fuera de rango
                try:
                    if hasattr(obj, "marca_fuera_de_rango"):
                        obj.marca_fuera_de_rango()
                        obj.save(update_fields=["fuera_de_rango"])
                except Exception:
                    pass

                if created:
                    resultados["resultados_creados"] += 1

            # Actualizar estado de la orden
            try:
                if orden.estado == "Pendiente":
                    orden.estado = "En validación"
                    orden.save(update_fields=["estado"])
            except Exception as e:
                resultados["errores"].append(f"Error actualizando estado de orden {num_orden}: {str(e)}")

            # Actualizar estado de OrdenExamen
            try:
                OrdenExamen.objects.filter(orden=orden).exclude(estado="Validado").update(estado="Procesado")
            except Exception as e:
                resultados["errores"].append(f"Error actualizando estado de OrdenExamen: {str(e)}")

            # Marcar mensaje como procesado
            msg.estado = "procesado"
            msg.save(update_fields=["estado"])

        resultados["detalle"].append({
            "mensaje_id": msg.id,
            "sample_id": num_orden,
            "estado": "ok",
            "mensaje": f"Procesado con {len(items)} OBX"
        })

    return resultados
