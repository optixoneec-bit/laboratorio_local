# configuracion/listener_thread.py

import socket
import threading
import traceback

from django.core.files.base import ContentFile
from .models import HL7Mensaje, HL7Imagen

from configuracion.decoders.genrui_decoder import GenruiImageDecoder


LISTENER_RUNNING = False
LISTENER_THREAD = None

PORT = 2575

START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"


def parse_hl7(raw):
    try:
        text = raw.decode(errors="ignore")
        lines = text.split("\r")

        msh = next((l for l in lines if l.startswith("MSH")), "")
        pid = next((l for l in lines if l.startswith("PID")), "")
        obr = next((l for l in lines if l.startswith("OBR")), "")
        obx = "\n".join([l for l in lines if l.startswith("OBX")])

        sample_id = ""
        exam_codes = ""

        try:
            if obr:
                parts = obr.split("|")
                sample_id = parts[3] if len(parts) > 3 else ""
                exam_codes = parts[4] if len(parts) > 4 else ""
        except:
            pass

        return msh, pid, obr, obx, sample_id, exam_codes

    except Exception:
        return "", "", "", "", "", ""


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

        # ED components
        comp = valor_ed.split("^")
        if len(comp) < 5:
            return

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
                            msh=msh,
                            pid=pid,
                            obr=obr,
                            obx=obx,
                            sample_id=sample_id,
                            exam_codes=exam_codes,
                            estado="pendiente",
                        )

                        # Procesar imágenes
                        if obx:
                            for linea in obx.split("\n"):
                                if "|ED|" in linea:
                                    guardar_imagen_desde_obx(msg, linea)

                        # ACK
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
