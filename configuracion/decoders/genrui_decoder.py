# configuracion/decoders/genrui_decoder.py

import base64
from io import BytesIO
from PIL import Image


class GenruiImageDecoder:
    """
    Decoder oficial para imágenes provenientes de equipos Genrui KT-6610 por HL7.
    Convierte RAW (sin header) + Base64 → PNG válido.

    Requiere:
        - Imagen USB real para referencia (ya obtenida).
        - Dimensiones confirmadas: 255 x 255 px.
        - Profundidad: 24 bits (RGB).
    """

    WIDTH = 255
    HEIGHT = 255
    BYTES_PER_PIXEL = 3  # 24 bits RGB

    @classmethod
    def decode_hl7_raw(cls, valor_ed: str) -> bytes:
        """
        Toma el componente ED completo de HL7:
            ^Image^BMP^Base64^AAAA....

        Devuelve los bytes PNG listos para guardar.
        """

        # Extraer el Base64
        partes = valor_ed.split("^")

        if len(partes) < 5:
            raise ValueError("ED no contiene Base64 válido")

        b64 = "".join(partes[4:]).strip()
        raw = base64.b64decode(b64)

        # Verificar tamaño esperado
        expected_size = cls.WIDTH * cls.HEIGHT * cls.BYTES_PER_PIXEL
        if len(raw) != expected_size:
            raise ValueError(
                f"El tamaño RAW ({len(raw)}) no coincide con {expected_size} bytes"
            )

        # Convertir RAW → PNG usando PIL
        img = Image.frombytes(
            mode="RGB",
            size=(cls.WIDTH, cls.HEIGHT),
            data=raw,
            decoder_name="raw"
        )

        # Guardar como PNG en buffer
        output = BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()
