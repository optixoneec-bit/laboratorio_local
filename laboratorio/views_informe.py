# laboratorio/views_informe.py

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from .models import Orden, OrdenExamen, Resultado
import os
import math
import re

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

    # ----------------------------- CABECERA -----------------------------
    def _draw_header(self):
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

        # Obtener exámenes ordenados por área y nombre
        examenes = (
            OrdenExamen.objects.filter(orden=self.orden)
            .select_related("examen")
            .prefetch_related("resultados")
            .order_by("examen__area", "examen__nombre")
        )

        # Agrupar por área
        grupos = {}
        for ex in examenes:
            area = ex.examen.area or "OTROS"
            grupos.setdefault(area, []).append(ex)

        # Dibujar área -> examen -> parámetros
        for area, examenes_area in grupos.items():
            # Título del área
            self.c.setFont("Helvetica-Bold", 9)
            titulo = area
            titulo_width = self.c.stringWidth(titulo, "Helvetica-Bold", 9)
            self.c.drawString((self.width - titulo_width) / 2, self.y_current, titulo)
            self.y_current -= 12

            for ex in examenes_area:
                # Nombre del examen como subtítulo
                self.c.setFont("Helvetica-Bold", 9)
                self.c.drawString(self.left, self.y_current, ex.examen.nombre)
                self.y_current -= 12

                # Parámetros
                for r in ex.resultados.all():
                    self.c.setFont("Helvetica", 9)
                    self.c.drawString(self.left + 0, self.y_current, r.parametro or "")
                    self.c.drawString(self.left + 200, self.y_current, r.valor or "-")
                    self.c.drawString(self.left + 290, self.y_current, r.unidad or "")
                    self.c.drawString(self.left + 400, self.y_current, r.referencia or "")
                    self.y_current -= 12

                    # Líneas adicionales debajo del examen (método, observación, verificado)
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

                self.y_current -= 6  # espacio después del examen

            self.y_current -= 10  # espacio después del área

    # ----------------------------- HL7 → GRÁFICAS -----------------------------
    def _get_hl7_message_for_order(self):
        """
        Intenta localizar un HL7Mensaje que corresponda a esta orden.
        """
        try:
            from configuracion.models import HL7Mensaje
        except Exception:
            return None

        sample_candidates = []
        if getattr(self.orden, "numero_orden", None):
            sample_candidates.append(str(self.orden.numero_orden))
        sample_candidates.append(str(self.orden.id))

        try:
            msg = (
                HL7Mensaje.objects
                .filter(sample_id__in=sample_candidates)
                .order_by("-id")
                .first()
            )
            return msg
        except Exception:
            return None

    def _parse_hist_binary(self, raw):
        """
        '16711680;0,0,1,2,5,...' -> lista de enteros [0,0,1,2,5,...]
        """
        if not raw:
            return None
        try:
            parts = str(raw).split(";")
            if len(parts) < 2:
                return None
            values = [
                int(x) for x in parts[1].split(",") if x.strip() != ""
            ]
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

    # ----------------------------- SECCIÓN DE GRÁFICAS ---------------------------
    def _draw_graphs_section(self):
        """
        Sección 'Gráficas del equipo'.
        RBC / PLT / DIFF / BASO en una sola fila, con más espacio entre ellas.
        """
        msg = self._get_hl7_message_for_order()
        if not msg:
            return

        raw = msg.mensaje_raw or ""
        if not raw:
            return

        rbc_hist_raw = None
        plt_hist_raw = None
        diff_raw = None
        baso_raw = None

        # Extraer las cadenas Binary desde el HL7
        for line in str(raw).splitlines():
            line = line.strip()
            if not line.startswith("OBX|"):
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            obs_id = parts[3] or ""
            val = (parts[5] or "").strip()
            if not val:
                continue

            if "RBC Histogram.Binary" in obs_id:
                rbc_hist_raw = val
            elif "PLT Histogram.Binary" in obs_id:
                plt_hist_raw = val
            elif "DIFFScatter.Binary" in obs_id or "DIFF Scatter.Binary" in obs_id:
                diff_raw = val
            elif "BASOScatter.Binary" in obs_id or "BASO Scatter.Binary" in obs_id:
                baso_raw = val

        if not any([rbc_hist_raw, plt_hist_raw, diff_raw, baso_raw]):
            return

        # Parseo
        rbc_values  = self._parse_hist_binary(rbc_hist_raw)  if rbc_hist_raw else None
        plt_values  = self._parse_hist_binary(plt_hist_raw)  if plt_hist_raw else None
        diff_groups = self._parse_scatter_binary(diff_raw)   if diff_raw else None
        baso_groups = self._parse_scatter_binary(baso_raw)   if baso_raw else None

        if not any([rbc_values, plt_values, diff_groups, baso_groups]):
            return

        # Título sección
        self.y_current -= 20
        self.c.setFont("Helvetica-Bold", 10)
        self.c.setFillColor(colors.black)
        self.c.drawString(self.left, self.y_current, "Gráficas del equipo")
        self.y_current -= 18

        # Layout: 4 columnas en una fila, con GAP entre gráficas
        block_height = 80
        total_width = (self.right - self.left) - 20
        gap = 25  # espacio entre gráficas

        col_width = (total_width - (gap * 3)) / 4.0

        x0 = self.left + 10
        y_graph = self.y_current - block_height - 10
        if y_graph < 120:
            y_graph = 120

        # RBC
        if rbc_values:
            self._draw_hist(x0, y_graph, col_width, block_height, rbc_values, "RBC")

        # PLT
        if plt_values:
            self._draw_hist(x0 + col_width + gap, y_graph, col_width, block_height, plt_values, "PLT")

        # DIFF (scatter)
        if diff_groups:
            self._draw_scatter(
                x0 + (col_width + gap) * 2,
                y_graph,
                col_width,
                block_height,
                diff_groups,
                "DIFF",
                baso=False,
            )

        # BASO (scatter)
        if baso_groups:
            self._draw_scatter(
                x0 + (col_width + gap) * 3,
                y_graph,
                col_width,
                block_height,
                baso_groups,
                "BASO",
                baso=True,
            )

        self.y_current = y_graph - 30

    # ----------------------------- FOOTER -----------------------------
    def _draw_footer(self):

        # Línea divisoria
        self.c.setStrokeColor(colors.gray)
        self.c.setLineWidth(0.4)
        self.c.line(self.left, 60, self.right, 60)

        # Disclaimer
        self.c.setFont("Helvetica", 7)
        self.c.setFillColor(colors.black)

        disclaimer_1 = (
            "Se considera el punto (.) como separador decimal para todos los exámenes."
        )
        disclaimer_2 = (
            "La fecha de nacimiento corresponde a la información entregada por el paciente o el laboratorio remitente."
        )

        self.c.drawCentredString(self.width / 2, 92, disclaimer_1)
        self.c.drawCentredString(self.width / 2, 82, disclaimer_2)

        # Número de página (por ahora fijo 1 de 1)
        self.c.setFont("Helvetica", 7)
        self.c.setFillColor(colors.gray)
        self.c.drawString(self.left, 40, f"Página {self.page_number} de 1")

    # ----------------------------- GENERAR REPORTE COMPLETO ------------------------
    def generate_report(self):
        self._draw_header()
        self._draw_patient_and_order_data()
        self._draw_results()
        # Gráficas del equipo
        self._draw_graphs_section()
        self._draw_footer()
        self.c.showPage()
        self.c.save()

# --- VISTA DE DJANGO ---

@login_required
def imprimir_informe(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="informe_orden_{orden.numero_orden or orden.id}.pdf"'
    )

    c = canvas.Canvas(response, pagesize=A4)

    report_generator = InformeCanvas(c, orden)
    report_generator.generate_report()

    return response
