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


def _msh_get_parts(msh_line: str):
    try:
        return (msh_line or "").split("|")
    except Exception:
        return []


def _msh_get_message_type(msh_line: str) -> str:
    try:
        parts = _msh_get_parts(msh_line)
        return (parts[8] or "").strip() if len(parts) > 8 else ""
    except Exception:
        return ""


def _msh_get_control_id(msh_line: str) -> str:
    try:
        parts = _msh_get_parts(msh_line)
        return (parts[9] or "").strip() if len(parts) > 9 else ""
    except Exception:
        return ""


def _msh_get_sending(msh_line: str):
    try:
        parts = _msh_get_parts(msh_line)
        sending_app = (parts[2] or "").strip() if len(parts) > 2 else ""
        sending_fac = (parts[3] or "").strip() if len(parts) > 3 else ""
        return sending_app, sending_fac
    except Exception:
        return "", ""


def construir_ack(msh_in: str, ack_code: str = "AA", text: str = "") -> bytes:
    now = datetime.now().strftime("%Y%m%d%H%M%S")

    in_type = _msh_get_message_type(msh_in)
    in_ctrl = _msh_get_control_id(msh_in) or "1"
    in_sending_app, in_sending_fac = _msh_get_sending(msh_in)

    trigger = ""
    try:
        if "^" in in_type:
            trigger = in_type.split("^", 1)[1].strip()
    except Exception:
        trigger = ""

    ack_type = f"ACK^{trigger}" if trigger else "ACK"
    out_ctrl = f"SRV{now}"

    msh = f"MSH|^~\\&|LAB|FAC|{in_sending_app}|{in_sending_fac}|{now}||{ack_type}|{out_ctrl}|P|2.3.1"

    if text:
        msa = f"MSA|{ack_code}|{in_ctrl}|{text}"
    else:
        msa = f"MSA|{ack_code}|{in_ctrl}"

    return f"{msh}\r{msa}\r".encode("utf-8")


def construir_respuesta_consulta(sample_id, msh_in=""):
    """
    Busca la orden en Django y construye un mensaje HL7 (ADR^A19)
    ajustado a los modelos reales y al equipo Genrui KT-6610.
    """
    try:
        from laboratorio.models import Orden 
        # Buscamos la orden por el numero_orden que envió el equipo
        orden = Orden.objects.filter(numero_orden=sample_id).select_related('paciente').first()
        now = datetime.now().strftime("%Y%m%d%H%M%S")

        in_ctrl = _msh_get_control_id(msh_in) or "1"
        in_sending_app, in_sending_fac = _msh_get_sending(msh_in)

        msh = f"MSH|^~\\&|LAB|FAC|{in_sending_app}|{in_sending_fac}|{now}||ADR^A19|SRV{now}|P|2.3.1"
        
        if not orden or not orden.paciente:
            # Si no hay orden, respondemos un error de registro no encontrado
            msa = f"MSA|AE|{in_ctrl}|Orden {sample_id} no encontrada"
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

        msa = f"MSA|AA|{in_ctrl}"
        # El segmento QRD debe repetir el ID de muestra que el equipo pidió
        qrd = f"QRD|{now}|R|I|Q100|||1^RD|{sample_id}|OTH"

        # PID:
        # - PID-2: colocamos el sample_id (para equipos que lo toman desde ahí)
        # - PID-3: colocamos la cédula (ID real del paciente)
        pid = f"PID|1|{sample_id}||{p.documento_identidad}||{nombre_hl7}||{f_nac}|{sexo_hl7}"
        
        hl7_resp = f"{msh}\r{msa}\r{qrd}\r{pid}\r"
        return hl7_resp.encode("utf-8")
        
    except Exception as e:
        print(f"DEBUG - Error en construir_respuesta_consulta: {e}")
        return construir_ack(msh_in or "", "AE", "Error Interno en Servidor")


def parse_hl7(raw):
    try:
        text = raw.decode(errors="ignore")
        lines = text.split("\r")

        msh = next((l for l in lines if l.startswith("MSH")), "")
        pid = next((l for l in lines if l.startswith("PID")), "")
        obr = next((l for l in lines if l.startswith("OBR")), "")
        qrd = next((l for l in lines if l.startswith("QRD")), "")
        orc = next((l for l in lines if l.startswith("ORC")), "")
        obx = "\n".join([l for l in lines if l.startswith("OBX")])

        sample_id = ""
        exam_codes = ""

        try:
            if obr:
                parts = obr.split("|")
                # OJO: en tu HL7 real el sample_id ya te funciona como '001013'
                # y está llegando bien por aquí (en tu BD ya vimos sample_id lleno).
                # (Algunos equipos lo mandan en OBR-3 u OBR-2)
                sample_id = ""
                if len(parts) > 3 and parts[3]:
                    sample_id = parts[3]
                elif len(parts) > 2 and parts[2]:
                    sample_id = parts[2]
                exam_codes = parts[4] if len(parts) > 4 else ""

            if not sample_id and orc:
                parts = orc.split("|")
                # ORC-3 suele traer el ID de muestra/orden en Genrui (ej: ORC|RF|C1|001000||IP)
                sample_id = parts[3] if len(parts) > 3 else ""

            if not sample_id and pid:
                parts = pid.split("|")
                # PID|1||001000||...  -> PID-3 = 001000 (si el equipo lo manda ahí)
                sample_id = parts[3] if len(parts) > 3 else ""

            if not sample_id and qrd:
                parts = qrd.split("|")
                sample_id = parts[8] if len(parts) > 8 else ""

            if sample_id:
                sample_id = (sample_id.split("^")[0] or "").strip()

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

            try:
                seq = int(parts[1])
            except Exception:
                seq = 0

            vtype = (parts[2] or "").strip()
            obx3  = (parts[3] or "").strip()
            val   = (parts[5] or "").strip()
            unit  = (parts[6] or "").strip() if len(parts) > 6 else ""
            ref   = (parts[7] or "").strip() if len(parts) > 7 else ""

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

    try:
        from django.db import transaction, models
    except Exception:
        return {"ok": False, "reason": "no_importa_django_db", "creados": 0, "actualizados": 0, "ignorados": 0}

    try:
        from laboratorio.models import Orden, OrdenExamen, Resultado
    except Exception:
        return {"ok": False, "reason": "no_importa_modelos_laboratorio", "creados": 0, "actualizados": 0, "ignorados": 0}

    orden = Orden.objects.filter(numero_orden=sample_id).first()
    if not orden:
        return {"ok": False, "reason": "sin_orden", "creados": 0, "actualizados": 0, "ignorados": 0}

    equipo = None
    try:
        if msg.ip_equipo:
            equipo = Equipo.objects.filter(activo=True, host=str(msg.ip_equipo).strip()).order_by("id").first()
    except Exception:
        equipo = None
    if not equipo:
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

    items = _extract_obx_items(msg.mensaje_raw or "")
    if not items:
        return {"ok": False, "reason": "sin_obx", "creados": 0, "actualizados": 0, "ignorados": 0}

    creados = 0
    actualizados = 0
    ignorados = 0

    with transaction.atomic():
        for it in items:
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

            if not mp.examen:
                ignorados += 1
                continue

            param = (mp.parametro or "").strip()
            if not param:
                ignorados += 1
                continue

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

        if creados > 0 or actualizados > 0:
            msg.estado = "procesado"

            try:
                if getattr(orden, "estado", None) != "En validación":
                    orden.estado = "En validación"
                    orden.save(update_fields=["estado"])
            except Exception:
                pass

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
        server_socket.settimeout(1.0)
        LISTENER_RUNNING = True

        while LISTENER_RUNNING:
            try:
                conn, addr = server_socket.accept()
            except socket.timeout:
                continue

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

                        raw_text = hl7_message.decode(errors="ignore")
                        msh, pid, obr, obx, sample_id, exam_codes = parse_hl7(hl7_message)

                        msg = HL7Mensaje.objects.create(
                            ip_equipo=addr[0],
                            mensaje_raw=raw_text,
                            msh=msh, pid=pid, obr=obr, obx=obx,
                            sample_id=sample_id, exam_codes=exam_codes,
                            estado="pendiente",
                        )

                        msg_type = _msh_get_message_type(msh)
                        has_qrd = ("QRD|" in raw_text)

                        is_query = False
                        try:
                            if has_qrd:
                                is_query = True
                            elif "QRY" in msg_type or "QBP" in msg_type:
                                is_query = True
                            elif ("ORM" in msg_type) and (not obx):
                                is_query = True
                        except Exception:
                            is_query = False

                        if is_query:
                            respuesta = construir_respuesta_consulta(sample_id, msh)
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

                            ack = construir_ack(msh, "AA")
                            conn.send(START_BLOCK + ack + END_BLOCK + b"\x0d")
                        
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
