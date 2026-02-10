import socket

# Como es tu PC, usamos localhost
IP = "127.0.0.1" 
PUERTO = 2575

# Formato MLLP que tu código espera (\x0b al inicio, \x1c\x0d al final)
def probar(id_orden):
    # Trama de consulta que tu parse_hl7 reconocerá como QRY
    mensaje = f"MSH|^~\\&|EQUIPO|LAB|||2026||QRY^Q02|1|P|2.3.1\rQRD|2026|R|I|Q100|||1^RD|{id_orden}|OTH\r"
    trama = b"\x0b" + mensaje.encode() + b"\x1c\x0d"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((IP, PUERTO))
        sock.sendall(trama)
        respuesta = sock.recv(4096)
        print(f"\nRespuesta del servidor:\n{respuesta.decode(errors='ignore')}")
        sock.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    id_test = input("Ingresa un numero_orden que exista en tu DB: ")
    probar(id_test)