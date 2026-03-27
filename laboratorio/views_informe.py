# laboratorio/views_informe.py

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from .models import Orden, OrdenExamen, Resultado
import os
import math
import re
import io
from io import BytesIO

# Importar matplotlib para gráficas
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------------------
#   CLASE PRINCIPAL PARA DIBUJAR EL INFORME PDF
# ----------------------------------------------------------------------------------

class InformeCanvas:

    def __init__(self, c, orden):
        self.c = c
        self.orden = orden
        self.width, self.height = A4
        self.left = 60
        self.right = self.width - 60
        self.y_current = self.height - 60
        self.line_height = 12
        self.col_mid = (self.left + self.right) / 2
        self.page_number = 1

        # Colores base
        # Ejes: gris oscuro (se quita el magenta fuerte)
        self.color_axis = colors.Color(0.2, 0.2, 0.2)
        # Curva de histograma
        self.color_curve = colors.Color(0, 0.8, 1)
        # Fallback para DIFF/BASO
        self.color_diff_points = colors.Color(0, 0.7, 1)
        self.color_baso_points = colors.Color(0, 0.9, 0.7)

    # ----------------------------- PAGE BREAK UTILITIES -----------------------------
    def _check_page_break(self, required_space, for_footer=False):
        """
        Verifica si hay espacio suficiente en la página actual.
        Si no lo hay, crea una nueva página.
        
        Args:
            required_space: espacio mínimo necesario en puntos
            for_footer: si True, usa margen mayor parafooter/firma
        """
        # Margen inferior de la página
        # Aumentar margen cuando es para footer/firma (evitar choques)
        if for_footer:
            margin_bottom = 120  # Mayor margen parafooter y firma
        else:
            margin_bottom = 80
        
        if self.y_current - required_space < margin_bottom:
            # Dibujar footer antes de cambiar de página (solo si ya no es la primera página)
            if self.page_number > 0:
                self._draw_footer()
            
            # Crear nueva página
            self.c.showPage()
            self.page_number += 1
            
            # Reiniciar posición Y en la nueva página
            self.y_current = self.height - 60
            
            # DIBUJAR ENCABEZADO COMPLETO (HEADER + DATOS) INMEDIATAMENTE DESPUÉS DE showPage()
            self._draw_complete_top()
            
            return True
        return False

    def _force_new_page(self):
        """Fuerza una nueva página y dibuja el encabezado."""
        self.c.showPage()
        self.page_number += 1
        self.y_current = self.height - 10
        # Dibujar el encabezado completo en la nueva página
        self._draw_complete_top()

    # ----------------------------- UTILIDADES -----------------------------
    def _calculate_age(self):
        if self.orden.paciente.fecha_nacimiento:
            today = timezone.now().date()
            born = self.orden.paciente.fecha_nacimiento
            edad = today.year - born.year - (
                (today.month, today.day) < (born.month, born.day)
            )
            return f"{edad} años"
        return "—"

    def _draw_text_wrapped(self, text, x, y, max_width, font_name="Helvetica", font_size=9):
        self.c.setFont(font_name, font_size)
        textobject = self.c.beginText(x, y)
        textobject.setFont(font_name, font_size)

        words = str(text).split(" ")
        line = ""
        y_initial = y

        for word in words:
            test_line = (line + " " + word).strip()
            if self.c.stringWidth(test_line, font_name, font_size) < max_width:
                line += " " + word
            else:
                textobject.textLine(line.strip())
                line = word

        textobject.textLine(line.strip())
        self.c.drawText(textobject)

        num_lines = len(textobject.getLines())
        return y_initial - (num_lines * self.line_height)

    def _norm_area(self, s):
        """
        Normaliza el texto de área para comparar sin depender de mayúsculas/acentos.
        """
        if not s:
            return ""
        t = str(s).strip().upper()
        # normalización simple de acentos comunes
        t = (t.replace("Á", "A")
               .replace("É", "E")
               .replace("Í", "I")
               .replace("Ó", "O")
               .replace("Ú", "U")
               .replace("Ü", "U")
               .replace("Ñ", "N"))
        return t

    # ----------------------------- CABECERA -----------------------------
    def _draw_header(self):
        # Usar ruta absoluta desde MEDIA_ROOT o configuración estática
        base_dir = getattr(settings, 'BASE_DIR', None)
        if base_dir:
            logo_path = os.path.join(
                base_dir, "laboratorio", "static", "laboratorio", "img", "logo_confianza.png"
            )
        else:
            # Fallback: usar directorio base del archivo
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logo_path = os.path.join(
                base_dir, "laboratorio", "static", "laboratorio", "img", "logo_confianza.png"
            )

        logo_width = 260
        logo_y = self.height - 130  # posición vertical del logo

        try:
            logo = ImageReader(logo_path)
            logo_x = (self.width / 2) - (logo_width / 2)

            self.c.drawImage(
                logo,
                logo_x,
                logo_y,
                width=logo_width,
                preserveAspectRatio=True,
                mask="auto"
            )
        except Exception as e:
            print("NO SE PUDO CARGAR LOGO:", e)

        # Título
        self.c.setFont("Helvetica-Bold", 12)
        title = "Informe de Resultados de Laboratorio"
        tw = self.c.stringWidth(title, "Helvetica-Bold", 12)
        self.c.drawString((self.width - tw) / 2, logo_y - -35, title)

        # Espacio después de cabecera
        self.y_current = logo_y - -5

    # ----------------------------- DATOS DEL PACIENTE -----------------------------
    def _draw_patient_and_order_data(self):

        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(self.left, self.y_current, "Datos del Paciente")
        self.c.drawString(self.col_mid, self.y_current, "Datos de la Orden")

        self.y_current -= 12

        datos_paciente = [
            ("Nombre", self.orden.paciente.nombre_completo),
            ("Documento", self.orden.paciente.documento_identidad),
            ("Edad", self._calculate_age()),
            ("Teléfono", self.orden.paciente.telefono or "—"),
            ("Email", self.orden.paciente.email or "—"),
            ("Dirección", self.orden.paciente.direccion or "—"),
        ]

        # obtener nombre del usuario que validó (si existe)
        validador_nombre = None
        try:
            resultado_validado = (
                Resultado.objects
                .filter(orden_examen__orden=self.orden, validado=True)
                .select_related("validado_por")
                .order_by("fecha_validacion")
                .last()
            )
            if resultado_validado and resultado_validado.validado_por:
                usuario = resultado_validado.validado_por
                if hasattr(usuario, "get_full_name"):
                    validador_nombre = usuario.get_full_name() or str(usuario)
                else:
                    validador_nombre = str(usuario)
        except Exception:
            validador_nombre = None

        datos_orden = [
            ("N° Orden", self.orden.numero_orden),
            ("Fecha", self.orden.fecha.strftime("%d/%m/%Y %H:%M")),
            ("Tipo", self.orden.tipo),
            ("Estado", self.orden.estado),
        ]

        # Agregar médico si existe
        if self.orden.medico:
            datos_orden.append(("Médico", self.orden.medico))

        if validador_nombre:
            datos_orden.append(("Validado por", validador_nombre))

        max_filas = max(len(datos_paciente), len(datos_orden))
        y = self.y_current

        for i in range(max_filas):
            if i < len(datos_paciente):
                self.c.setFont("Helvetica-Bold", 9)
                self.c.drawString(self.left, y, f"{datos_paciente[i][0]}:")
                self.c.setFont("Helvetica", 9)
                self.c.drawString(self.left + 70, y, str(datos_paciente[i][1]))

            if i < len(datos_orden):
                self.c.setFont("Helvetica-Bold", 9)
                self.c.drawString(self.col_mid, y, f"{datos_orden[i][0]}:")
                self.c.setFont("Helvetica", 9)
                self.c.drawString(self.col_mid + 70, y, str(datos_orden[i][1]))

            y -= self.line_height

        self.y_current = y - 1
        self.c.line(self.left, self.y_current, self.right, self.y_current)
        self.y_current -= 20

    # ----------------------------- CABECERA COMPLETA (HEADER + DATOS) -------------
    def _draw_complete_top(self):
        """
        Dibuja el encabezado completo: header + datos del paciente y orden.
        Se usa al inicio del reporte y después de cada salto de página.
        """
        self._draw_header()
        self._draw_patient_and_order_data()

    # ----------------------------- CABECERA RESULTADOS -----------------------------
    def _draw_results_header(self):
        self.c.setFillColor(colors.lightgrey)
        self.c.rect(self.left, self.y_current, self.right - self.left, 14, fill=1, stroke=0)
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica-Bold", 9)

        self.c.drawString(self.left + 5, self.y_current + 3, "Examen")
        self.c.drawString(self.left + 190, self.y_current + 3, "Resultado")
        self.c.drawString(self.left + 270, self.y_current + 3, "Unidad")
        self.c.drawString(self.left + 380, self.y_current + 3, "Referencia")

        self.y_current -= 18
        self.c.setFont("Helvetica", 9)

    # ----------------------------- RESULTADOS AGRUPADOS POR ÁREA ------------------
    def _draw_results(self):
        self.c.setFont("Helvetica-Bold", 11)
        self.c.drawString(self.left, self.y_current, "Resultados de Exámenes")
        self.y_current -= 18

        self._draw_results_header()

        # Obtener exámenes
        examenes = (
            OrdenExamen.objects.filter(orden=self.orden)
            .select_related("examen")
            .prefetch_related("resultados")
            .order_by("examen__nombre")
        )

        # Agrupar por área
        grupos = {}
        for ex in examenes:
            area = ex.examen.area or "OTROS"
            grupos.setdefault(area, []).append(ex)

        # Ordenar áreas: Hematología primero, luego Coagulación, luego el resto (A-Z)
        prioridad = {
            "HEMATOLOGIA": 0,
            "HEMATOLOGÍA": 0,
            "HEMATOLOGIA Y COAGULACION": 0,
            "HEMATOLOGÍA Y COAGULACIÓN": 0,
            "COAGULACION": 1,
            "COAGULACIÓN": 1,
        }

        def area_sort_key(area_name):
            norm = self._norm_area(area_name)
            pr = prioridad.get(norm, 2)
            return (pr, norm)

        areas_ordenadas = sorted(grupos.keys(), key=area_sort_key)

        # ================================================================
        # NUEVO ORDEN: A) Biometría Hemática -> B) Gráficas -> C) Otros
        # ================================================================
        
        # A) PRIMERO: Dibujar solo Biometría Hemática (Hematología)
        biometria_norm = {"HEMATOLOGIA", "HEMATOLOGÍA", "HEMATOLOGIA Y COAGULACION", "HEMATOLOGÍA Y COAGULACIÓN"}
        
        for area in areas_ordenadas:
            norm_area = self._norm_area(area)
            if norm_area not in biometria_norm:
                continue  # Skip - se dibujará después
            
            examenes_area = grupos[area]
            
            # Page break antes del área si no hay espacio suficiente
            self._check_page_break(100)

            # Título del área
            self.c.setFont("Helvetica-Bold", 9)
            titulo = area
            titulo_width = self.c.stringWidth(titulo, "Helvetica-Bold", 9)
            self.c.drawString((self.width - titulo_width) / 2, self.y_current, titulo)
            self.y_current -= 12

            for ex in examenes_area:
                # Page break antes del examen si no hay espacio suficiente
                self._check_page_break(80)

                # Nombre del examen como subtítulo
                self.c.setFont("Helvetica-Bold", 9)
                self.c.drawString(self.left, self.y_current, ex.examen.nombre)
                self.y_current -= 12

                # Parámetros - evaluar QuerySet UNA sola vez
                resultados_list = list(ex.resultados.all().order_by('id'))
                
                # Eliminar duplicados por parámetro
                seen_params = {}
                exam_name_lower = (ex.examen.nombre or '').strip().lower()
                for r in resultados_list:
                    param_key = (r.parametro or '').strip().lower()
                    if param_key == exam_name_lower:
                        continue
                    if param_key not in seen_params:
                        seen_params[param_key] = r
                
                resultados_unicos = list(seen_params.values())
                
                # Para biometría: extraer método y observación del primer resultado que los tenga
                # y mostrarlos DESPUÉS del título, UNA sola vez
                biometria_metodo = None
                biometria_obs = None
                # Solo para áreas de biometría
                if norm_area in biometria_norm:
                    for r in resultados_unicos:
                        if getattr(r, 'metodo', None) and not biometria_metodo:
                            biometria_metodo = r.metodo
                        if getattr(r, 'observacion', None) and not biometria_obs:
                            biometria_obs = r.observacion
                        if biometria_metodo and biometria_obs:
                            break
                    
                    # Dibujar método y observación DESPUÉS del título (UNA sola vez para biometría)
                    if biometria_metodo or biometria_obs:
                        extra_y = self.y_current
                        self.c.setFont("Helvetica-Oblique", 7)
                        if biometria_metodo:
                            self.c.drawString(self.left + 0, extra_y, f"Método: {biometria_metodo}")
                            extra_y -= 9
                        if biometria_obs:
                            self.c.drawString(self.left + 0, extra_y, f"Obs.: {biometria_obs}")
                            extra_y -= 9
                        self.y_current = extra_y
                
                for r in resultados_unicos:
                    self._check_page_break(40)

                    self.c.setFont("Helvetica", 9)
                    self.c.drawString(self.left + 0, self.y_current, r.parametro or "")
                    self.c.drawString(self.left + 200, self.y_current, r.valor or "-")
                    self.c.drawString(self.left + 290, self.y_current, r.unidad or "")
                    self.c.drawString(self.left + 400, self.y_current, r.referencia or "")
                    self.y_current -= 12

                    # Para OTROS exámenes (no biometría): dibujar método/observación por cada resultado
                    # Para biometría ya se dibujaron antes del loop
                    if norm_area not in biometria_norm:
                        extra_y = self.y_current - 0
                        self.c.setFont("Helvetica-Oblique", 7)

                        if getattr(r, "metodo", None):
                            self.c.drawString(self.left + 0, extra_y, f"Método: {r.metodo}")
                            extra_y -= 9

                        if getattr(r, "observacion", None):
                            self.c.drawString(self.left + 0, extra_y, f"Obs.: {r.observacion}")
                            extra_y -= 9

                        if getattr(r, "verificado", False):
                            self.c.drawString(self.left + 0, extra_y, "Verificado")
                            extra_y -= 9

                        self.y_current = extra_y - 3

                self.y_current -= 6

            self.y_current -= 10

        # B) SEGUNDO: Dibujar las GRÁFICAS después de Biometría
        self._draw_histograms_after_hematology()

        # C) TERCERO: Dibujar los demás exámenes (no Hematología/Coagulación)
        for area in areas_ordenadas:
            norm_area = self._norm_area(area)
            if norm_area in biometria_norm:
                continue  # Ya dibujado
            
            examenes_area = grupos[area]
            
            # Page break antes del área si no hay espacio suficiente
            self._check_page_break(100)

            # Título del área
            self.c.setFont("Helvetica-Bold", 9)
            titulo = area
            titulo_width = self.c.stringWidth(titulo, "Helvetica-Bold", 9)
            self.c.drawString((self.width - titulo_width) / 2, self.y_current, titulo)
            self.y_current -= 12

            for ex in examenes_area:
                # Page break antes del examen si no hay espacio suficiente
                self._check_page_break(80)

                # Nombre del examen como subtítulo
                self.c.setFont("Helvetica-Bold", 9)
                self.c.drawString(self.left, self.y_current, ex.examen.nombre)
                self.y_current -= 12

                # Parámetros
                resultados_list = list(ex.resultados.all().order_by('id'))
                
                seen_params = {}
                exam_name_lower = (ex.examen.nombre or '').strip().lower()
                for r in resultados_list:
                    param_key = (r.parametro or '').strip().lower()
                    if param_key == exam_name_lower:
                        continue
                    if param_key not in seen_params:
                        seen_params[param_key] = r
                
                resultados_unicos = list(seen_params.values())
                
                for r in resultados_unicos:
                    self._check_page_break(40)

                    self.c.setFont("Helvetica", 9)
                    self.c.drawString(self.left + 0, self.y_current, r.parametro or "")
                    self.c.drawString(self.left + 200, self.y_current, r.valor or "-")
                    self.c.drawString(self.left + 290, self.y_current, r.unidad or "")
                    self.c.drawString(self.left + 400, self.y_current, r.referencia or "")
                    self.y_current -= 12

                    extra_y = self.y_current - 0
                    self.c.setFont("Helvetica-Oblique", 7)

                    if getattr(r, "metodo", None):
                        self.c.drawString(self.left + 0, extra_y, f"Método: {r.metodo}")
                        extra_y -= 9

                    if getattr(r, "observacion", None):
                        self.c.drawString(self.left + 0, extra_y, f"Obs.: {r.observacion}")
                        extra_y -= 9

                    if getattr(r, "verificado", False):
                        self.c.drawString(self.left + 0, extra_y, "Verificado")
                        extra_y -= 9

                    self.y_current = extra_y - 3

                self.y_current -= 6

            self.y_current -= 10

    # ----------------------------- HL7 → GRÁFICAS -----------------------------
    def _get_hl7_message_for_order(self):
        """
        Intenta localizar un HL7Mensaje que corresponda a esta orden.
        Prioriza mensajes ORU^R01 (contienen resultados e histogramas).
        """
        try:
            from configuracion.models import HL7Mensaje
        except Exception:
            return None

        numero_orden = ""
        if getattr(self.orden, "numero_orden", None) is not None:
            numero_orden = str(self.orden.numero_orden).strip()

        orden_id = str(self.orden.id).strip()

        # Candidatos comunes (exactos)
        candidates = []
        if numero_orden:
            candidates.append(numero_orden)
            # sin ceros a la izquierda (muy común en equipos)
            candidates.append(numero_orden.lstrip("0") or numero_orden)
        candidates.append(orden_id)

        # 1) PRIORIZAR mensajes ORU^R01 (contienen histogramas/scatter)
        # IMPORTANTE: Usar order_by("id") para obtener el más ANTIGUO (primeros datos del equipo)
        try:
            # Buscar primero mensajes ORU^R01
            qs = HL7Mensaje.objects.filter(sample_id__in=candidates)
            msg = qs.filter(mensaje_raw__contains='ORU^R01').order_by("id").first()
            if msg:
                return msg
        except Exception:
            pass

        # 2) Intento exacto (cualquier tipo de mensaje)
        try:
            msg = (
                HL7Mensaje.objects
                .filter(sample_id__in=candidates)
                .order_by("id")
                .first()
            )
            if msg:
                return msg
        except Exception:
            pass

        # 3) Intento flexible (si el sample_id tiene prefijos/sufijos)
        #    Ej: "ORD-000123", "000123A", "123/2026", etc.
        try:
            qs = HL7Mensaje.objects.all()
            if numero_orden:
                qs = qs.filter(sample_id__icontains=numero_orden)
                # Priorizar ORU^R01 - primero el más antiguo
                msg = qs.filter(mensaje_raw__contains='ORU^R01').order_by("id").first()
                if msg:
                    return msg
                msg = qs.order_by("id").first()
                if msg:
                    return msg
        except Exception:
            pass

        return None

    def _parse_hist_binary(self, raw):
        """
        '16711680;0,0,1,2,5,...' -> lista de enteros [0,0,1,2,5,...]
        Formato del HL7: color_int;val1,val2,val3,...
        
        MEJORA: Limpieza agresiva para extraer CUALQUIER número decimal del mensaje.
        Maneja formatos como:
        - "(0, 0, 1, 2, 5, ...)"
        - "16711680;0,0,1,2,5,..."
        - "16711680,0,0,1,2,5,..." 
        - "0,0,1,2,5,..."
        """
        if not raw:
            return None
        try:
            s = str(raw).strip()
            if not s:
                return None

            # LIMPIEZA AGRESIVA: extraer CUALQUIER número del mensaje
            # Esto maneja formatos como: "(0, 0, 1, 2, 5, ...)" o "16711680;(0,0,1,2,5)"
            
            # Primero, eliminar paréntesis y corchetes
            s = s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
            
            # El formato puede ser:
            # 1) "16711680;0,0,1,2,5,..."
            # 2) "16711680,0,0,1,2,5,..." (sin punto y coma)
            # 3) "65280;0,0,7,23,49,..."
            # 4) "0,0,1,2,5,..." (solo valores)
            
            # Buscar el punto y coma o la coma después del número de color
            values_str = None
            if ";" in s:
                parts = s.split(";")
                if len(parts) >= 2:
                    values_str = parts[1]
                else:
                    return None
            elif "," in s:
                # Puede ser "16711680,0,0,1,2" o "0,0,1,2,5"
                # Primero verificar si el primer valor es un número de color (mayor a 65535)
                parts = s.split(",")
                try:
                    first_val = int(parts[0])
                    if first_val > 65535:
                        # Es un color, los valores empiezan desde el índice 1
                        values_str = ",".join(parts[1:])
                    else:
                        # Es una lista de valores directa
                        values_str = s
                except ValueError:
                    values_str = s
            else:
                # Solo un número - no es válido para histograma
                return None
            
            if not values_str:
                return None
            
            # Parsear los valores - extraer todos los números enteros
            values = []
            for x in values_str.split(","):
                x = x.strip()
                if x:
                    try:
                        values.append(int(x))
                    except ValueError:
                        # Si falla con int, intentar con float y convertir
                        try:
                            values.append(int(float(x)))
                        except:
                            continue
            
            if not values:
                return None
            return values
        except Exception:
            return None

    def _parse_scatter_binary(self, raw):
        """
        '16711680,(10,20)(30,40);255,(5,5)(6,7)' ->
        [{'color': Color, 'points': [(x,y), ...]}, ...]
        """
        if not raw:
            return None

        s = str(raw).strip()
        if not s:
            return None

        groups = []

        for chunk in re.split(r"[;|]", s):
            c = chunk.strip()
            if not c:
                continue

            m = re.match(r"^(\d+),?", c)
            if not m:
                continue

            try:
                color_int = int(m.group(1))
            except ValueError:
                color_int = 0

            r_v = ((color_int >> 16) & 0xFF) / 255.0
            g_v = ((color_int >> 8) & 0xFF) / 255.0
            b_v = (color_int & 0xFF) / 255.0
            color = colors.Color(r_v, g_v, b_v)

            rest = c[m.end():]
            points = []
            for x_str, y_str in re.findall(r"\((\d+),(\d+)\)", rest):
                try:
                    x = int(x_str)
                    y = int(y_str)
                    points.append((x, y))
                except ValueError:
                    continue

            if points:
                groups.append({"color": color, "points": points})

        if not groups:
            return None

        return groups

    # ----------------------------- GRÁFICAS: HISTOGRAMAS -------------------------
    def _draw_hist(self, x, y, width, height, values, label):
        """
        Histograma estilo equipo:
        - Ejes tipo "L".
        - Escalas específicas para RBC y PLT (0–300 / 0–40) con 'fL'.
        """
        if not values:
            return

        max_val = max(values) if values else 1
        if max_val <= 0:
            max_val = 1

        n = len(values)
        if n < 2:
            return

        # Curva principal
        self.c.setStrokeColor(self.color_curve)
        self.c.setLineWidth(1)

        step = width / float(n - 1)

        px_prev = None
        py_prev = None
        for i, v in enumerate(values):
            px = x + i * step
            py = y + (v / max_val) * (height - 6)
            if px_prev is None:
                px_prev, py_prev = px, py
            else:
                self.c.line(px_prev, py_prev, px, py)
                px_prev, py_prev = px, py

        # Ejes tipo "L"
        self.c.setStrokeColor(self.color_axis)
        self.c.setLineWidth(0.7)
        self.c.line(x, y, x, y + height)      # eje Y
        self.c.line(x, y, x + width, y)       # eje X

        # Escalas específicas
        self.c.setFont("Helvetica", 6)
        self.c.setFillColor(colors.black)

        if label == "RBC":
            x_max = 300.0
            ticks = [0, 100, 200,]
            dashed = [100, 300]
        elif label == "PLT":
            x_max = 40.0
            ticks = [0, 10, 20, 30,]
            dashed = [10, 30]
        else:
            x_max = float(n - 1)
            ticks = [0, int(x_max / 2), int(x_max)]
            dashed = []

        # Líneas verticales punteadas
        for val in dashed:
            if x_max <= 0:
                continue
            px = x + (val / x_max) * width
            self.c.setStrokeColor(self.color_axis)
            self.c.setDash(1, 2)
            self.c.line(px, y, px, y + height)
            self.c.setDash()

        # Ticks y números en eje X
        for val in ticks:
            if x_max <= 0:
                continue
            px = x + (val / x_max) * width
            self.c.setStrokeColor(self.color_axis)
            self.c.setLineWidth(0.5)
            self.c.line(px, y, px, y + 3)
            self.c.setFillColor(colors.black)
            self.c.drawCentredString(px, y - 8, str(val))

        # Unidad fL
        if label in ("RBC", "PLT"):
            self.c.setFont("Helvetica", 7)
            self.c.drawRightString(x + width, y - 8, "fL")

        # Título arriba (centrado)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.setFillColor(colors.black)
        title_w = self.c.stringWidth(label, "Helvetica-Bold", 9)
        self.c.drawString(x + (width - title_w) / 2.0, y + height + 4, label)

    # ----------------------------- GRÁFICAS: SCATTER -----------------------------
    def _draw_scatter(self, x, y, width, height, data, label, baso=False):
        """
        Scatter:
        - data: [{'color': Color, 'points': [(x,y), ...]}, ...]
        - Ejes tipo "L", LAS / MAS, título (DIFF / BASO).
        """
        if not data:
            return

        # Soporte legacy: lista simple de puntos
        if data and isinstance(data[0], tuple):
            default_color = self.color_baso_points if baso else self.color_diff_points
            groups = [{"color": default_color, "points": data}]
        else:
            groups = data

        all_points = []
        for g in groups:
            all_points.extend(g["points"])
        if not all_points:
            return

        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        if max_x == min_x:
            max_x = min_x + 1
        if max_y == min_y:
            max_y = min_y + 1

        # Puntos
        self.c.setLineWidth(0)
        for group in groups:
            col = group.get("color") or (self.color_baso_points if baso else self.color_diff_points)
            self.c.setFillColor(col)
            for (px, py) in group["points"]:
                nx = x + (px - min_x) / (max_x - min_x) * (width - 4) + 2
                ny = y + (py - min_y) / (max_y - min_y) * (height - 4) + 2
                self.c.circle(nx, ny, 0.7, stroke=0, fill=1)

        # Ejes tipo "L"
        self.c.setStrokeColor(self.color_axis)
        self.c.setLineWidth(0.7)
        self.c.line(x, y, x, y + height)      # eje Y
        self.c.line(x, y, x + width, y)       # eje X

        # Texto LAS / MAS
        self.c.setFont("Helvetica-Bold", 7)
        self.c.setFillColor(colors.black)
        self.c.drawString(x + 2, y + height + 4, "LAS")
        self.c.drawRightString(x + width, y - 8, "MAS")

        # Título centrado arriba
        self.c.setFont("Helvetica-Bold", 9)
        title_w = self.c.stringWidth(label, "Helvetica-Bold", 9)
        self.c.drawString(x + (width - title_w) / 2.0, y + height + 4, label)

    # ----------------------------- SECCIÓN DE GRÁFICAS (HISTOGRAMAS + SCATTER) ---------
    def _draw_histograms_after_hematology(self):
        """
        Dibuja las 4 gráficas de Hematología (RBC, PLT, DIFF, BASO) después de los resultados.
        Layout: 4 gráficas en línea horizontal (de margen izquierdo a derecho).
        - RBC: histograma
        - PLT: histograma
        - DIFF: scatter plot
        - BASO: scatter plot
        
        Usa canvas puro. Si no hay datos HL7, no hace nada.
        
        IMPORTANTE: Fuerza una nueva página antes de dibujar las gráficas
        para que siempre aparezcan después de los resultados de exámenes.
        """
        # Buscar mensaje HL7 para esta orden
        hl7_msg = self._get_hl7_message_for_order()

        # Extraer datos de histogramas y scatter del mensaje HL7
        rbc_values = None
        plt_values = None
        diff_values = None
        baso_values = None

        if hl7_msg and hl7_msg.mensaje_raw:
            mensaje = hl7_msg.mensaje_raw
            # Usar el formato especificado: mensaje.replace("\r", "\n").split("\n")
            lines = mensaje.replace("\r", "\n").split("\n")

            for line in lines:
                line = line.strip()
                if not line.startswith('OBX|'):
                    continue

                # RBC Histogram - buscar 'RBC Histogram.Binary' (OBX|58|)
                if 'RBC Histogram.Binary' in line or 'RBC  Histogram.Binary' in line:
                    rbc_values = self._extract_histogram_value(line)

                # PLT Histogram - buscar 'PLT Histogram.Binary' (OBX|64|)
                elif 'PLT Histogram.Binary' in line or 'PLT  Histogram.Binary' in line:
                    plt_values = self._extract_histogram_value(line)

                # DIFF Scatter - buscar 'DIFFScatter.Binary' o '^DIFF Scatter^'
                elif 'DIFFScatter.Binary' in line or 'DIFF Scatter.Binary' in line:
                    diff_values = self._extract_scatter_value(line)

                # BASO Scatter - buscar 'BASOScatter.Binary' o '^BASO Scatter^'
                elif 'BASOScatter.Binary' in line or 'BASO Scatter.Binary' in line:
                    baso_values = self._extract_scatter_value(line)

        # Verificar si hay datos para dibujar
        has_data = (rbc_values is not None and len(rbc_values) > 0) or \
                   (plt_values is not None and len(plt_values) > 0) or \
                   (diff_values is not None and len(diff_values) > 0) or \
                   (baso_values is not None and len(baso_values) > 0)

        # Si no hay datos, NO hacer nada
        if not has_data:
            return

        # FUERZA NUEVA PÁGINA antes de dibujar las gráficas
        # para que siempre aparezcan después de los resultados de exámenes
        self._force_new_page()

        # Espacio de 10 puntos antes de las gráficas (para evitar que queden pegadas al encabezado)
        self.y_current -= 10

        # Configurar 4 gráficas en línea horizontal (de margen a margen)
        total_width = self.right - self.left  # Ancho disponible
        graph_spacing = 10  # Espacio entre gráficas
        graph_width = (total_width - 3 * graph_spacing) / 4  # 4 gráficas
        graph_height = 90
        y_pos = self.y_current - graph_height + 15

        # Posiciones X para las 4 gráficas evenly spaced
        x_positions = [
            self.left,  # RBC
            self.left + graph_width + graph_spacing,  # PLT
            self.left + 2 * (graph_width + graph_spacing),  # DIFF
            self.left + 3 * (graph_width + graph_spacing),  # BASO
        ]

        # RBC Histograma (gráfica 1)
        if rbc_values and len(rbc_values) > 0:
            self._draw_hist(x_positions[0], y_pos, graph_width, graph_height, rbc_values, "RBC")

        # PLT Histograma (gráfica 2)
        if plt_values and len(plt_values) > 0:
            self._draw_hist(x_positions[1], y_pos, graph_width, graph_height, plt_values, "PLT")

        # DIFF Scatter (gráfica 3)
        if diff_values and len(diff_values) > 0:
            self._draw_scatter(x_positions[2], y_pos, graph_width, graph_height, diff_values, "DIFF", baso=False)

        # BASO Scatter (gráfica 4)
        if baso_values and len(baso_values) > 0:
            self._draw_scatter(x_positions[3], y_pos, graph_width, graph_height, baso_values, "BASO", baso=True)

        # Actualizar posición Y después de las gráficas
        self.y_current = y_pos - 40

    def _extract_scatter_value(self, line):
        """
        Extrae los valores de scatter plot de una línea OBX.
        Formato: color_int,(x1,y1)(x2,y2);color2,(x3,y3)...
        """
        if not line:
            return None

        try:
            # Buscar el valor en OBX-5
            parts = line.split('|')
            if len(parts) < 6:
                return None

            value_field = parts[5].strip()
            if not value_field:
                return None

            # Usar _parse_scatter_binary para procesar
            return self._parse_scatter_binary(value_field)

        except Exception as e:
            print(f"Error extrayendo scatter: {e}")
            return None

    def _extract_histogram_value(self, line):
        """
        Extrae los valores del histograma de una línea OBX.
        Formato: color_int;val1,val2,val3,... o (val1,val2,val3,...)
        """
        if not line:
            return None

        try:
            # Buscar el valor después del '||' (OBX-5)
            parts = line.split('|')
            if len(parts) < 6:
                return None

            value_field = parts[5].strip()
            if not value_field:
                return None

            # El valor puede tener el formato: "16711680;0,0,1,2,5,..."
            # o "(0, 0, 1, 2, 5, ...)"
            # o "16711680,(0,0,1,2,5,...)" - formato con paréntesis

            # Limpiar paréntesis y corchetes
            value_field = value_field.replace('(', '').replace(')', '').replace('[', '').replace(']', '')

            # Buscar el punto y coma o la coma
            if ';' in value_field:
                values_part = value_field.split(';', 1)[1]
            elif ',' in value_field:
                # Verificar si el primer valor es un color (mayor a 65535)
                first_comma = value_field.index(',')
                try:
                    first_val = int(value_field[:first_comma])
                    if first_val > 65535:
                        values_part = value_field[first_comma + 1:]
                    else:
                        values_part = value_field
                except ValueError:
                    values_part = value_field
            else:
                return None

            if not values_part:
                return None

            # Parsear valores
            values = []
            for x in values_part.split(','):
                x = x.strip()
                if x:
                    try:
                        values.append(int(x))
                    except ValueError:
                        try:
                            values.append(int(float(x)))
                        except:
                            continue

            if values:
                return values

        except Exception as e:
            print(f"Error extrayendo histograma: {e}")

        return None

    def _draw_histogram_matplotlib(self, x, y, width, height, values, label):
        """
        Dibuja un histograma usando matplotlib y lo inserta en el PDF.
        """
        if not values or len(values) < 2:
            return

        try:
            # Crear figura con matplotlib
            fig, ax = plt.subplots(figsize=(width/72, height/72), dpi=72)
            ax.clear()

            # Configurar fondo blanco
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')

            # Dibujar histograma
            x_vals = list(range(len(values)))
            ax.fill_between(x_vals, values, color='#00CCFF', alpha=0.7)
            ax.plot(x_vals, values, color='#0088CC', linewidth=0.8)

            # Configurar ejes
            ax.set_xlim(0, len(values) - 1)
            max_val = max(values) if values else 1
            ax.set_ylim(0, max_val * 1.1)

            # Ocultar ticks y etiquetas
            ax.set_xticks([])
            ax.set_yticks([])

            # Dibujar ejes tipo "L"
            ax.spines['left'].set_visible(True)
            ax.spines['left'].set_color('#333333')
            ax.spines['left'].set_linewidth(0.7)

            ax.spines['bottom'].set_visible(True)
            ax.spines['bottom'].set_color('#333333')
            ax.spines['bottom'].set_linewidth(0.7)

            ax.spines['right'].set_visible(False)
            ax.spines['top'].set_visible(False)

            # Título
            ax.set_title(label, fontsize=9, fontweight='bold', pad=2)

            # Configurar escala según el tipo
            if label == "RBC":
                ax.set_xlim(0, 300)
                # Agregar ticks para 0, 100, 200
                ax.set_xticks([0, 100, 200, 300])
                ax.set_xticklabels(['0', '100', '200', ''], fontsize=6)
                ax.set_xlabel('fL', fontsize=7)
            elif label == "PLT":
                ax.set_xlim(0, 40)
                ax.set_xticks([0, 10, 20, 30, 40])
                ax.set_xticklabels(['0', '10', '20', '30', '40'], fontsize=6)
                ax.set_xlabel('fL', fontsize=7)

            plt.tight_layout(pad=0.3)

            # Guardar en BytesIO
            buf = BytesIO()
            plt.savefig(buf, format='png', transparent=True, dpi=72)
            buf.seek(0)

            # Insertar imagen en PDF
            img = ImageReader(buf)
            self.c.drawImage(img, x, y, width=width, height=height, mask='auto')

            plt.close(fig)
            buf.close()

        except Exception as e:
            print(f"Error dibujando histograma {label}: {e}")

    # ----------------------------- FOOTER -----------------------------
    def _draw_footer(self):
        # NO llamar a _check_page_break aquí - ya se verificó antes
        # Solo dibujar el footer

        # Línea divisoria
        self.c.setStrokeColor(colors.gray)
        self.c.setLineWidth(0.4)
        self.c.line(self.left, 60, self.right, 60)

        # Disclaimer con mejor espaciado
        self.c.setFont("Helvetica", 7)
        self.c.setFillColor(colors.black)

        disclaimer_1 = (
            "Se considera el punto (.) como separador decimal para todos los exámenes."
        )
        disclaimer_2 = (
            "La fecha de nacimiento corresponde a la información entregada por el paciente o el laboratorio remitente."
        )

        # Ajustar posiciones Y para evitar amontonamiento
        self.c.drawCentredString(self.width / 2, 95, disclaimer_1)
        self.c.drawCentredString(self.width / 2, 85, disclaimer_2)

        # Número de página dinámico
        self.c.setFont("Helvetica", 7)
        self.c.setFillColor(colors.gray)
        self.c.drawString(self.left, 40, f"Página {self.page_number}")

    # ----------------------------- GENERAR REPORTE COMPLETO ------------------------
    def generate_report(self):
        self._draw_complete_top()
        self._draw_results()
        self._draw_footer()
        self.c.showPage()
        self.c.save()

# --- VISTA DE DJANGO ---

@login_required
def imprimir_informe(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)

    # Print de debug: mostrar la ruta/nombre del archivo que se está generando
    filename = "RESULTADO_GRAFICAS_NUEVO.pdf"
    print(f"[DEBUG] Generando PDF: {filename}")
    print(f"[DEBUG] Ruta del archivo (HttpResponse stream): en memoria (no se guarda en disco)")
    print(f"[DEBUG] Content-Disposition: inline; filename=\"{filename}\"")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{filename}"'
    )

    c = canvas.Canvas(response, pagesize=A4)

    report_generator = InformeCanvas(c, orden)
    report_generator.generate_report()

    return response
