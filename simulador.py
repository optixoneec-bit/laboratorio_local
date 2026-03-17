import socket
import sys
from datetime import datetime

# Configuración de conexión
IP = "127.0.0.1"
PUERTO = 2575


def enviar_resultados_hl7(numero_orden, documento_paciente=None, nombre_paciente=None, 
                          fecha_nacimiento=None, sexo=None, resultados=None):
    """
    Envía mensaje HL7 ORU^R01 directamente al listener.
    
    Estructura del mensaje:
    - MSH: Header del mensaje
    - PID: Datos del paciente (opcional)
    - ORC: Order Common - número de orden en posición 2
    - OBR: Observation Request - número de orden en posición 3
    - OBX: Resultados de laboratorio
    
    El flujo estándar es: El simulador envía los resultados directamente,
    sin necesidad de consulta previa (QRY).
    """
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    control_id = f"ORD{now}"
    
    # Valores por defecto si no se proporcionan
    if not documento_paciente:
        documento_paciente = ""
    if not nombre_paciente:
        nombre_paciente = "PACIENTE^NOMBRE"
    if not fecha_nacimiento:
        fecha_nacimiento = ""
    if not sexo:
        sexo = "U"
    
    # Convertir nombre a formato HL7 (Apellido^Nombre) si es necesario
    if nombre_paciente and "^" not in nombre_paciente and " " in nombre_paciente:
        partes = nombre_paciente.split(" ", 1)
        nombre_hl7 = f"{partes[1]}^{partes[0]}"
    else:
        nombre_hl7 = nombre_paciente
    
    # Convertir fecha de nacimiento a formato HL7 (YYYYMMDD)
    if fecha_nacimiento:
        fecha_nac_hl7 = fecha_nacimiento.replace("-", "").replace("/", "")
    else:
        fecha_nac_hl7 = ""
    
    # Construir segmento PID (datos del paciente)
    pid = f"PID|1||{documento_paciente}||{nombre_hl7}||{fecha_nac_hl7}|{sexo}"
    
    # Construir segmento ORC (Order Common) - Número de orden en posición 2
    # ORC|1|NUMERO_ORDEN|...  -> posición 2 = Placer Order Number
    orc = f"ORC|NW|{numero_orden}|||IP"
    
    # Construir segmento OBR (Observation Request) - Número de orden en posición 3
    # OBR|1|NUMERO_ORDEN|...
    obr = f"OBR|1|{numero_orden}|{now}||{now}||||||"
    
    # Construir segmentos OBX (resultados)
    obx_lines = []
    if resultados:
        for i, resultado in enumerate(resultados, start=1):
            codigo = resultado.get("codigo", "")
            valor = resultado.get("valor", "")
            unidad = resultado.get("unidad", "")
            referencia = resultado.get("referencia", "")
            
            if codigo and valor:
                # Formato OBX: OBX|secuencia|tipo|código|valor|unidad|referencia|...
                obx = f"OBX|{i}|NM|^{codigo}^{codigo}||{valor}|{unidad}|{referencia}|N|||F"
                obx_lines.append(obx)
    else:
        # Resultados de ejemplo si no se proporcionan
        obx_lines = [
            f"OBX|1|NM|^WBC^WBC||5.42|10^9/L|4.00-10.00|N|||F",
            f"OBX|2|NM|^RBC^RBC||4.50|10^12/L|4.00-5.50|N|||F",
            f"OBX|3|NM|^HGB^HGB||14.0|g/dL|12.0-16.0|N|||F",
            f"OBX|4|NM|^HCT^HCT||42|%|36-50|N|||F",
            f"OBX|5|NM|^PLT^PLT||250|10^9/L|100-400|N|||F",
        ]
    
    obx_segment = "\r".join(obx_lines)
    
    # Construir mensaje HL7 completo
    # Estructura: MSH -> PID -> ORC -> OBR -> OBX
    mensaje = (
        f"MSH|^~\\&|EQUIPO|LAB|||{now}||ORU^R01|{control_id}|P|2.3.1\r"
        f"{pid}\r"
        f"{orc}\r"
        f"{obr}\r"
        f"{obx_segment}"
    )
    
    # Envolver en delimitadores MLLP
    trama = b"\x0b" + mensaje.encode("utf-8") + b"\x1c\x0d"
    
    return trama, mensaje


def probar(numero_orden, documento=None, nombre=None, fecha_nac=None, sexo=None, resultados=None):
    """
    Envía mensaje HL7 de resultados al listener y espera ACK.
    """
    print(f"\n{'='*50}")
    print(f"SIMULADOR DE EQUIPO - Envío de Resultados HL7")
    print(f"{'='*50}")
    print(f"Conectando a: {IP}:{PUERTO}")
    print(f"Número de Orden: {numero_orden}")
    print(f"Documento: {documento or 'No proporcionado'}")
    print(f"Nombre: {nombre or 'No proporcionado'}")
    print(f"{'='*50}")
    
    try:
        # Construir mensaje HL7
        trama, mensaje = enviar_resultados_hl7(
            numero_orden=numero_orden,
            documento_paciente=documento,
            nombre_paciente=nombre,
            fecha_nacimiento=fecha_nac,
            sexo=sexo,
            resultados=resultados
        )
        
        print("\n[MENSAJE HL7 A ENVIAR]")
        print("-" * 50)
        print(mensaje)
        print("-" * 50)
        
        # Conectar y enviar
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((IP, PUERTO))
        
        print("\nEnviando mensaje HL7...")
        sock.sendall(trama)
        
        # Recibir ACK
        respuesta = sock.recv(4096)
        respuesta_raw = respuesta.decode("utf-8", errors="ignore")
        
        print("\n[RESPUESTA DEL SERVIDOR]")
        print("-" * 50)
        print(respuesta_raw)
        print("-" * 50)
        
        # Verificar ACK
        if "MSA|AA|" in respuesta_raw:
            print("\n✅ ÉXITO: Mensaje procesado correctamente (ACK)")
            print(f"   Código de acknowledgment: AA (Application Accept)")
        elif "MSA|AE|" in respuesta_raw:
            print("\n⚠️ ERROR: Acknowledgment de error (AE)")
            # Extraer mensaje de error
            for linea in respuesta_raw.split("\r"):
                if linea.startswith("MSA|"):
                    partes = linea.split("|")
                    if len(partes) > 2:
                        print(f"   Mensaje: {partes[2]}")
        elif "MSA|AR|" in respuesta_raw:
            print("\n⚠️ ERROR: Rechazo de aplicación (AR)")
        else:
            print("\n⚠️ Respuesta desconocida del servidor")
        
        sock.close()
        
        print(f"\n{'='*50}")
        print("ENVÍO COMPLETADO")
        print(f"{'='*50}")
        
    except socket.timeout:
        print("\n❌ Error: Tiempo de espera agotado. ¿El listener está activo?")
        print("   Asegúrate de que el servidor Django esté corriendo.")
    except ConnectionRefusedError:
        print("\n❌ Error: Conexión rechazada.")
        print(f"   ¿El servidor está corriendo en el puerto {PUERTO}?")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def modo_interactivo():
    """Modo interactivo por consola."""
    print("=" * 50)
    print("  SIMULADOR DE EQUIPO - Laboratorio HL7")
    print("=" * 50)
    print("Este script simula un equipo médico que envía")
    print("resultados de exámenes vía HL7/MLLP")
    print("=" * 50)
    print("\nFormato estándar: ORU^R01")
    print("Segmentos: MSH -> PID -> ORC -> OBR -> OBX")
    print("=" * 50)
    
    while True:
        print("\n--- NUEVA SIMULACIÓN ---")
        numero_orden = input("Número de orden: ").strip()
        
        if not numero_orden:
            print("Por favor ingresa un número de orden.")
            continue
        
        if numero_orden.lower() == 'q':
            print("¡Hasta luego!")
            break
        
        # Datos opcionales del paciente
        print("\n[Datos del paciente - Presione Enter para omitir]")
        documento = input("Documento identidad: ").strip()
        nombre = input("Nombre paciente: ").strip()
        fecha_nac = input("Fecha nacimiento (YYYY-MM-DD): ").strip()
        sexo = input("Sexo (M/F): ").strip().upper()
        
        # Resultados personalizados o usar ejemplos
        print("\n[Resultados - Presione Enter para usar ejemplos]")
        print("¿Desea ingresar resultados personalizados? (s/n): ", end="")
        usar_ejemplos = input().strip().lower() != "s"
        
        resultados = None
        if not usar_ejemplos:
            resultados = []
            print("\nIngrese resultados (codigo, valor, unidad, referencia)")
            print("Ejemplo: WBC, 5.42, 10^9/L, 4.00-10.00")
            print("(Deje codigo vacío para terminar)")
            
            while True:
                entrada = input("Resultado: ").strip()
                if not entrada:
                    break
                
                partes = entrada.split(",")
                if len(partes) >= 2:
                    resultado = {
                        "codigo": partes[0].strip(),
                        "valor": partes[1].strip(),
                        "unidad": partes[2].strip() if len(partes) > 2 else "",
                        "referencia": partes[3].strip() if len(partes) > 3 else ""
                    }
                    resultados.append(resultado)
        
        probar(
            numero_orden=numero_orden,
            documento=documento if documento else None,
            nombre=nombre if nombre else None,
            fecha_nac=fecha_nac if fecha_nac else None,
            sexo=sexo if sexo else None,
            resultados=resultados
        )


if __name__ == "__main__":
    # Si se pasa argumento por línea de comandos, usarlo directamente
    if len(sys.argv) > 1:
        numero_orden = sys.argv[1]
        documento = sys.argv[2] if len(sys.argv) > 2 else None
        nombre = sys.argv[3] if len(sys.argv) > 3 else None
        fecha_nac = sys.argv[4] if len(sys.argv) > 4 else None
        sexo = sys.argv[5] if len(sys.argv) > 5 else None
        
        probar(
            numero_orden=numero_orden,
            documento=documento,
            nombre=nombre,
            fecha_nac=fecha_nac,
            sexo=sexo
        )
    else:
        modo_interactivo()
