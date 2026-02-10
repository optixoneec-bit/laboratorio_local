# configuracion/listener_thread.py

import socket
import threading
import traceback
from datetime import datetime

from django.core.files.base import ContentFile
from django.db import models
from django.db import transaction

from .models import HL7Mensaje, HL7Imagen, Equipo, EquipoMapeo
from configuracion.decoders.genrui_decoder import GenruiImageDecoder


LISTENER_RUNNING = False
LISTENER_THREAD = None

PORT = 2575

START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"


def construir_respuesta_consulta(sample_id):
    """
    Busca la orden en Django y construye un mensaje HL7 (ADR^A19)
    ajustado a los modelos reales y al equipo Genrui KT-6610.
    """
    try:
        from laboratorio.models import Orden 
        # Buscamos la orden por el numero_orden que envió el equipo
        orden = Orden.objects.filter(numero_orden=sample_id).select_related('paciente').first()
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        
        if not orden or not orden.paciente:
            # Si no hay orden, respondemos un error de registro no encontrado
            msh = f"MSH|^~\\&|LAB|FAC|||{now}||ADR^A19|1|P|2.3.1"
            msa = f"MSA|AE|Orden {sample_id} no encontrada"
            return f"{msh}\r{msa}\r".encode("utf-8")

        p = orden.paciente
        
        # AJUSTE A TU MODELO: Usamos nombre_completo
        # El equipo Genrui espera Apellido^Nombre, como tú tienes un solo campo,
        # lo enviamos completo en la posición del apellido para que lo muestre bien.
        nombre_hl7 = (p.nombre_completo or "PACIENTE SIN NOMBRE").upper()
        
        # AJUSTE DE SEXO: Tu modelo guarda 'M'/'F' (Masculino/Femenino)
        # El equipo espera M, F o U.
        sexo_hl7 = p.sexo if p.sexo in ['M', 'F'] else 'U'
        
        # AJUSTE DE FECHA: Formato YYYYMMDD
        f_nac = p.fecha_nacimiento.strftime("%Y%m%d") if p.fecha_nacimiento else ""

        # Construcción de la respuesta según manual Genrui
        msh = f"MSH|^~\\&|LAB|FAC|||{now}||ADR^A19|1|P|2.3.1"
        msa = "MSA|AA|1"
        # El segmento QRD debe repetir el ID de muestra que el equipo pidió
        qrd = f"QRD|{now}|R|I|Q100|||1^RD|{sample_id}|OTH"
        # Segmento PID con tu campo nombre_completo y documento_identidad
        pid = f"PID|1||{p.documento_identidad}||{nombre_hl7}||{f_nac}|{sexo_hl7}"
        
        hl7_resp = f"{msh}\r{msa}\r{qrd}\r{pid}\r"
        return hl7_resp.encode("utf-8")
        
    except Exception as e:
        # Esto saldrá en tu consola de Django si algo falla internamente
        print(f"DEBUG - Error en construir_respuesta_consulta: {e}")
        return b"MSH|^~\\&|LAB|FAC|||2026||ACK^Q02|1|P|2.3.1\rMSA|AE|Error Interno en Servidor\r"

def parse_hl7(raw):
    try:
        text = raw.decode(errors="ignore")
        lines = text.split("\r")

        msh = next((l for l in lines if l.startswith("MSH")), "")
        pid = next((l for l in lines if l.startswith("PID")), "")
        obr = next((l for l in lines if l.startswith("OBR")), "")
        qrd = next((l for l in lines if l.startswith("QRD")), "")
        obx = "\n".join([l for l in lines if l.startswith("OBX")])

        sample_id = ""
        exam_codes = ""

        try:
            if obr:
                parts = obr.split("|")
                # OJO: en tu HL7 real el sample_id ya te funciona como '001013'
                # y está llegando bien por aquí (en tu BD ya vimos sample_id lleno).
                sample_id = parts[3] if len(parts) > 3 else ""
                exam_codes = parts[4] if len(parts) > 4 else ""
            elif qrd:
                parts = qrd.split("|")
                sample_id = parts[8] if len(parts) > 8 else ""
        except Exception:
            pass

        return msh, pid, obr, obx, sample_id, exam_codes

    except Exception:
        return "", "", "", "", "", ""


def _parse_msh_fields(msh_line: str):
    """
    MSH|^~\&|SENDING_APP|SENDING_FACILITY|...
    """
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


def _infer_equipo(ip_equipo: str, msh_line: str):
    """
    Determina el Equipo (configuracion.Equipo) que envió el HL7.
    Prioridad:
      1) host == ip_equipo
      2) match por MSH sending_facility / sending_app contra codigo/modelo/nombre/fabricante
    """
    try:
        if ip_equipo:
            eq = Equipo.objects.filter(activo=True, host=str(ip_equipo).strip()).order_by("id").first()
            if eq:
                return eq
    except Exception:
        pass

    msh = _parse_msh_fields(msh_line or "")
    app = msh.get("sending_app", "")
    fac = msh.get("sending_facility", "")

    try:
        qs = Equipo.objects.filter(activo=True)
        # Buscamos coincidencias suaves
        if fac:
            qs = qs.filter(
                models.Q(codigo__icontains=fac) |
                models.Q(modelo__icontains=fac) |
                models.Q(nombre__icontains=fac)
            )
        if app:
            qs = qs.filter(
                models.Q(codigo__icontains=app) |
                models.Q(fabricante__icontains=app) |
                models.Q(nombre__icontains=app)
            )
        return qs.order_by("id").first()
    except Exception:
        return None


def _extract_obx_items(hl7_raw_text: str):
    """
    Devuelve items OBX respetando el ORDEN DEL EQUIPO (OBX-1):
      [
        {
          'seq': 1,
          'code': 'WBC',
          'value': '5.42',
          'unit': '10^9/L',
          'ref': '4.00-10.00',
          'type': 'NM',
          'raw_obx3': '^WBC^'
        },
        ...
      ]
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

            # 🔹 OBX-1 → SECUENCIA (ORDEN DEL EQUIPO)
            try:
                seq = int(parts[1])
            except Exception:
                seq = 0

            vtype = (parts[2] or "").strip()   # OBX-2
            obx3  = (parts[3] or "").strip()   # OBX-3
            val   = (parts[5] or "").strip()   # OBX-5
            unit  = (parts[6] or "").strip() if len(parts) > 6 else ""  # OBX-6
            ref   = (parts[7] or "").strip() if len(parts) > 7 else ""  # OBX-7

            parts3 = obx3.split("^")
            code = parts3[1].strip() if len(parts3) > 1 else ""

            if not code:
                continue

            items.append({
                "seq": seq,          # ✅ CLAVE: orden real del equipo
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
    Ignora OBX de gráficas/binarios:
      - Histogram / Scatter / .Binary
      - OBX-2 == ED (imágenes)
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


def _auto_cargar_resultados_desde_hl7(msg: HL7Mensaje):
    """
    AUTOMÁTICO:
      HL7Mensaje -> Orden(numero_orden == sample_id) -> aplica EquipoMapeo -> guarda Resultado
    REGLA:
      NO crea OrdenExamen si no existe (solo carga si la orden ya lo tiene).
    """
    sample_id = (msg.sample_id or "").strip()
    if not sample_id:
        return {"ok": False, "reason": "sin_sample_id", "creados": 0, "actualizados": 0, "ignorados": 0}

    # Importar utilidades DB (para evitar errores si el import global no está)
    try:
        from django.db import transaction, models
    except Exception:
        return {"ok": False, "reason": "no_importa_django_db", "creados": 0, "actualizados": 0, "ignorados": 0}

    # Importar modelos del laboratorio
    try:
        from laboratorio.models import Orden, OrdenExamen, Resultado
    except Exception:
        return {"ok": False, "reason": "no_importa_modelos_laboratorio", "creados": 0, "actualizados": 0, "ignorados": 0}

    orden = Orden.objects.filter(numero_orden=sample_id).first()
    if not orden:
        return {"ok": False, "reason": "sin_orden", "creados": 0, "actualizados": 0, "ignorados": 0}

    # Determinar equipo
    equipo = None
    try:
        # match por IP primero
        if msg.ip_equipo:
            equipo = Equipo.objects.filter(activo=True, host=str(msg.ip_equipo).strip()).order_by("id").first()
    except Exception:
        equipo = None

    if not equipo:
        # fallback por MSH
        try:
            msh_line = msg.msh or ""
            msh = _parse_msh_fields(msh_line)
            app = msh.get("sending_app", "")
            fac = msh.get("sending_facility", "")
            qs = Equipo.objects.filter(activo=True)

            if fac:
                qs = qs.filter(
                    models.Q(codigo__icontains=fac) |
                    models.Q(modelo__icontains=fac) |
                    models.Q(nombre__icontains=fac)
                )
            if app:
                qs = qs.filter(
                    models.Q(codigo__icontains=app) |
                    models.Q(fabricante__icontains=app) |
                    models.Q(nombre__icontains=app)
                )
            equipo = qs.order_by("id").first()
        except Exception:
            equipo = None

    if not equipo:
        return {"ok": False, "reason": "sin_equipo", "creados": 0, "actualizados": 0, "ignorados": 0}

    # Construir diccionario de mapeos por codigo_equipo (RESPETA MAYÚSCULAS)
    mapeos = (
        EquipoMapeo.objects
        .filter(equipo=equipo, activo=True)
        .select_related("examen")
        .all()
    )
    mapa = {}
    for mp in mapeos:
        if not mp.codigo_equipo:
            continue
        mapa[mp.codigo_equipo.strip()] = mp

    if not mapa:
        return {"ok": False, "reason": "sin_mapeos", "creados": 0, "actualizados": 0, "ignorados": 0}

    # Extraer OBX
    items = _extract_obx_items(msg.mensaje_raw or "")
    if not items:
        return {"ok": False, "reason": "sin_obx", "creados": 0, "actualizados": 0, "ignorados": 0}

    creados = 0
    actualizados = 0
    ignorados = 0

    with transaction.atomic():
        for it in items:
            # Ignorar binarios/gráficas/ED
            if _is_graph_or_binary_obx(it):
                ignorados += 1
                continue

            code = (it.get("code") or "").strip()
            if not code:
                ignorados += 1
                continue

            mp = mapa.get(code)
            if not mp:
                ignorados += 1
                continue

            # Debe existir examen y parametro interno
            if not mp.examen:
                ignorados += 1
                continue

            param = (mp.parametro or "").strip()
            if not param:
                ignorados += 1
                continue

            # REGLA: SOLO si ya existe OrdenExamen en la orden
            oe = OrdenExamen.objects.filter(orden=orden, examen=mp.examen).first()
            if not oe:
                ignorados += 1
                continue

            obj, created = Resultado.objects.update_or_create(
                orden_examen=oe,
                parametro=param,
                defaults={
                    "valor": it.get("value") if (it.get("value") or "").strip() != "" else None,
                    "unidad": it.get("unit") if (it.get("unit") or "").strip() != "" else None,
                    "referencia": it.get("ref") if (it.get("ref") or "").strip() != "" else None,
                    "orden_equipo": int(it.get("seq") or 0),
                }
            )

            # Marcar fuera de rango si aplica
            try:
                if hasattr(obj, "marca_fuera_de_rango"):
                    obj.marca_fuera_de_rango()
                    obj.save(update_fields=["fuera_de_rango"])
            except Exception:
                pass

            if created:
                creados += 1
            else:
                actualizados += 1

        # Estado del HL7Mensaje + flujo A (Orden/OrdenExamen)
        if creados > 0 or actualizados > 0:
            msg.estado = "procesado"

            # ✅ regla A: si llegaron resultados -> Orden a "En validación"
            try:
                if getattr(orden, "estado", None) != "En validación":
                    orden.estado = "En validación"
                    orden.save(update_fields=["estado"])
            except Exception:
                pass

            # ✅ para que aparezca en módulo Validación: OrdenExamen a "Procesado"
            try:
                OrdenExamen.objects.filter(orden=orden).exclude(estado="Validado").update(estado="Procesado")
            except Exception:
                pass

        else:
            msg.estado = "sin_resultados"

        msg.save(update_fields=["estado"])

    return {
        "ok": True,
        "reason": "ok",
        "creados": creados,
        "actualizados": actualizados,
        "ignorados": ignorados,
        "equipo": getattr(equipo, "codigo", ""),
        "orden_numero": orden.numero_orden,
        "orden_id": orden.id,
        "total_obx": len(items),
    }


def guardar_imagen_desde_obx(msg: HL7Mensaje, obx_linea: str) -> None:
    """
    Guarda una imagen PNG proveniente de un OBX tipo ED.
    """
    try:
        partes = obx_linea.split("|")
        if len(partes) < 6:
            return

        secuencia = (partes[1] or "").strip()
        codigo = (partes[3] or "").strip()
        valor_ed = (partes[5] or "").strip()

        # Decodificar RAW→PNG usando el decoder Genrui
        png_bytes = GenruiImageDecoder.decode_hl7_raw(valor_ed)

        nombre_logico = codigo.replace("^", "_") or "Imagen"
        filename = f"hl7_{msg.id}_{secuencia}_{nombre_logico}.png"

        imagen = HL7Imagen(
            mensaje=msg,
            tipo=nombre_logico,
            formato="png"
        )
        imagen.archivo.save(filename, ContentFile(png_bytes), save=True)

    except Exception as e:
        print("ERROR guardando imagen HL7:", e)


def listener_loop():
    global LISTENER_RUNNING

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind(("0.0.0.0", PORT))
        server_socket.listen(5)
        LISTENER_RUNNING = True

        while LISTENER_RUNNING:
            conn, addr = server_socket.accept()

            try:
                buffer = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break

                    buffer += chunk

                    if END_BLOCK in buffer:
                        start = buffer.find(START_BLOCK) + 1
                        end = buffer.find(END_BLOCK)
                        hl7_message = buffer[start:end]

                        msh, pid, obr, obx, sample_id, exam_codes = parse_hl7(hl7_message)

                        msg = HL7Mensaje.objects.create(
                            ip_equipo=addr[0],
                            mensaje_raw=hl7_message.decode(errors="ignore"),
                            msh=msh, pid=pid, obr=obr, obx=obx,
                            sample_id=sample_id, exam_codes=exam_codes,
                            estado="pendiente",
                        )

                        if "QRY" in msh:
                            respuesta = construir_respuesta_consulta(sample_id)
                            conn.send(START_BLOCK + respuesta + END_BLOCK + b"\x0d")
                        else:
                            if obx:
                                for linea in obx.split("\n"):
                                    if "|ED|" in linea:
                                        guardar_imagen_desde_obx(msg, linea)

                            try:
                                _auto_cargar_resultados_desde_hl7(msg)
                            except Exception:
                                traceback.print_exc()

                            conn.send(START_BLOCK + b"ACK|AA|\x1c\x0d")
                        
                        buffer = b""

                conn.close()
            except Exception:
                traceback.print_exc()
    except Exception:
        traceback.print_exc()
    finally:
        try:
            server_socket.close()
        except:
            pass
        LISTENER_RUNNING = False


def start_listener():
    global LISTENER_RUNNING, LISTENER_THREAD
    if LISTENER_RUNNING:
        return False
    LISTENER_THREAD = threading.Thread(target=listener_loop, daemon=True)
    LISTENER_THREAD.start()
    return True


def stop_listener():
    global LISTENER_RUNNING
    LISTENER_RUNNING = False
    return True


def status_listener():
    return LISTENER_RUNNING