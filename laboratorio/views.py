# laboratorio/views.py
import os
from datetime import date, datetime
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, FileResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string, get_template
from django.contrib.auth.views import redirect_to_login
from django.template import TemplateDoesNotExist
from io import BytesIO
from django.template.loader import render_to_string # NECESARIA
from collections import defaultdict # NECESARIA
from datetime import date
#from weasyprint import HTML, CSS # NECESARIA
from reportlab.graphics.barcode import code128
from django.core.files.base import ContentFile

from collections import defaultdict

from django.template.loader import render_to_string
from django.http import FileResponse
import tempfile
# -----------------------------------------------------------
# INFORME PDF — ESTILO SYNLAB — 100% REPORTLAB
# -----------------------------------------------------------
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle
from io import BytesIO


# -----------------------------
# PDF (ReportLab) — SOLO ESTO, COMO ORDENASTE
# -----------------------------
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader, simpleSplit

# -----------------------------
# Otros imports originales
# -----------------------------
import pandas as pd
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
import json
import csv
import io

# -----------------------------
# IMPORTACIÓN INCORRECTA, ELIMINADA:
# from weasyprint import HTML, CSS
# -----------------------------

from .models import Paciente
from django.forms.models import model_to_dict

try:
    import pandas as pd
except Exception:
    pd = None


from .models import Paciente, Orden, OrdenExamen, Resultado, Examen, ExamenParametro, Proforma, ProformaExamen


from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def calculate_age(birth_date):
    today = date.today()
    if isinstance(birth_date, date):
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return None

# ------------------------------
# Gestión de resultados y validación (TU CÓDIGO ORIGINAL)
# ------------------------------

@login_required
def registrar_resultado(request, orden_examen_id):
    """
    Guarda resultados individuales sin alterar el estado de la orden ni del examen.
    El estado solo cambiará cuando el usuario haga clic en 'Enviar a validación'.
    """
    orden_examen = get_object_or_404(OrdenExamen, id=orden_examen_id)
    if request.method == 'POST':
        parametro = request.POST.get('parametro')
        valor = request.POST.get('valor')
        unidad = request.POST.get('unidad')
        referencia = request.POST.get('referencia')
        metodo = request.POST.get('metodo')
        observacion = request.POST.get('observacion')
        verificado = request.POST.get('verificado') == 'True'

        if parametro and valor:
            Resultado.objects.create(
                orden_examen=orden_examen,
                parametro=parametro,
                valor=valor,
                unidad=unidad,
                referencia=referencia,
                metodo=metodo,
                observacion=observacion,
                verificado=verificado
            )
            # ❌ Ya no se cambia el estado aquí.
            return JsonResponse({'status': 'ok', 'message': 'Resultado registrado correctamente'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Datos incompletos'})
    return JsonResponse({'status': 'error', 'message': 'Solicitud inválida'})



@login_required
def validar_resultado(request, resultado_id):
    if not request.user.is_staff and not request.user.is_superuser:
        return HttpResponseForbidden("No tiene permisos para validar resultados")
    resultado = get_object_or_404(Resultado, id=resultado_id)
    resultado.validado = True
    resultado.validado_por = request.user
    resultado.fecha_validacion = timezone.now()
    resultado.save()
    orden_examen = resultado.orden_examen
    if not orden_examen.resultados.filter(validado=False).exists():
        orden_examen.estado = "Validado"
        orden_examen.save()
    orden = orden_examen.orden
    if not orden.examenes.filter(estado__in=["Pendiente", "Procesado"]).exists():
        orden.estado = "Validado"
        orden.save()
    return JsonResponse({'status': 'ok', 'message': 'Resultado validado correctamente'})


@login_required
def anular_validacion(request, resultado_id):
    if not request.user.is_staff and not request.user.is_superuser:
        return HttpResponseForbidden("No tiene permisos para anular validaciones")
    resultado = get_object_or_404(Resultado, id=resultado_id)
    resultado.validado = False
    resultado.validado_por = None
    resultado.fecha_validacion = None
    resultado.save()
    orden_examen = resultado.orden_examen
    orden_examen.estado = "Procesado"
    orden_examen.save()
    orden = orden_examen.orden
    orden.estado = "En proceso"
    orden.save()
    return JsonResponse({'status': 'ok', 'message': 'Validación anulada correctamente'})


# ------------------------------
# Vistas principales (TU CÓDIGO ORIGINAL)
# ------------------------------

@login_required
def lista_ordenes(request):
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    query = request.GET.get('q', '')
    desde = request.GET.get('desde')
    hasta = request.GET.get('hasta')

    ordenes = Orden.objects.all().order_by('-fecha')
    if query:
        ordenes = ordenes.filter(paciente__nombre_completo__icontains=query) | ordenes.filter(numero_orden__icontains=query)
    
    # Filtrar por fecha si se proporcionan
    if desde:
        ordenes = ordenes.filter(fecha__date__gte=desde)
    if hasta:
        ordenes = ordenes.filter(fecha__date__gte=hasta)

    # --- Estadísticas para gráficos ---
    # Órdenes por día (últimos 30 días)
    from datetime import timedelta
    thirty_days_ago = timezone.now() - timedelta(days=30)
    orders_by_day = (
        Orden.objects.filter(fecha__gte=thirty_days_ago)
        .annotate(day=TruncDate('fecha'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    chart_daily = {
        'labels': [o['day'].strftime('%d/%m') if o['day'] else '' for o in orders_by_day],
        'data': [o['count'] for o in orders_by_day]
    }

    # Distribución por estado
    orders_by_status = (
        Orden.objects.values('estado')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    chart_status = {
        'labels': [o['estado'] or 'Sin estado' for o in orders_by_status],
        'data': [o['count'] for o in orders_by_status]
    }

    # --- KPIs para las tarjetas ---
    kpis = {
        'total': Orden.objects.count(),
        'pendiente': Orden.objects.filter(estado='Pendiente').count(),
        'en_proceso': Orden.objects.filter(estado='En proceso').count(),
        'en_validacion': Orden.objects.filter(estado='En validación').count(),
        'validado': Orden.objects.filter(estado='Validado').count(),
    }

    return render(request, 'laboratorio/lista_ordenes.html', {
        'ordenes': ordenes,
        'query': query,
        'desde': desde or '',
        'hasta': hasta or '',
        'chart_daily': chart_daily,
        'chart_status': chart_status,
        'kpis': kpis,
    })


@login_required
def nueva_orden(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if request.method == 'POST':
        doc = request.POST.get('documento_identidad')
        nombre = request.POST.get('nombre_completo')
        paciente, _ = Paciente.objects.get_or_create(
            documento_identidad=doc,
            defaults={'nombre_completo': nombre, 'creado_por': request.user}
        )

        # === Número de orden: solo dígitos, inicia en 1000, ancho 6 (dos ceros delante) ===
        max_num = 999
        for s in Orden.objects.values_list('numero_orden', flat=True):
            ds = ''.join(ch for ch in (s or '') if ch.isdigit())
            if ds:
                try:
                    n = int(ds)
                    if n > max_num:
                        max_num = n
                except ValueError:
                    pass
        siguiente = max_num + 1           # → 1000 si no hay previas
        numero = f"{siguiente:06d}"       # → 001000, 001001, ...

        orden = Orden.objects.create(
            paciente=paciente,
            numero_orden=numero,
            creado_por=request.user
        )

        # -------------------------------------------
        # Guardar exámenes seleccionados (igual que tenías)
        # -------------------------------------------
        examenes_codigos = request.POST.getlist('examen_codigo[]')
        examenes_precios = request.POST.getlist('examen_precio[]')

        if examenes_codigos:
            for idx, codigo in enumerate(examenes_codigos):
                try:
                    ex = Examen.objects.get(codigo=codigo)
                    precio = float(examenes_precios[idx]) if idx < len(examenes_precios) else float(ex.precio)
                    OrdenExamen.objects.create(
                        orden=orden,
                        examen=ex,
                        precio=precio,
                        creado_por=request.user
                    )
                except Examen.DoesNotExist:
                    continue

        # --- NUEVO: si la acción es "etiquetas", generar PDF y devolverlo ---
        accion = (request.POST.get('accion') or '').strip().lower()
        if accion == 'etiquetas':
            pdf_bytes = _build_etiquetas_pdf_y_muestras(orden, request.user)
            filename = f"etiquetas_orden_{orden.id}.pdf"
            # (opcional) almacenar en media/
            default_storage.save(f"etiquetas/{filename}", ContentFile(pdf_bytes))
            # responder inline para imprimir
            resp = HttpResponse(pdf_bytes, content_type='application/pdf')
            resp['Content-Disposition'] = f'inline; filename="{filename}"'
            return resp

        # --- flujo normal ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('laboratorio/partials/orden_item.html', {'orden': orden})
            return JsonResponse({'status': 'ok', 'html': html})
        else:
            messages.success(request, f"Orden {numero} creada correctamente")
            return redirect('detalle_orden', orden_id=orden.id)
    return render(request, 'laboratorio/orden_form.html')



def _build_etiquetas_pdf_y_muestras(orden, user):
    """
    Genera:
      - 1 etiqueta general con código = orden.numero_orden
      - 1 etiqueta por cada OrdenExamen con sufijo .1, .2, ...
    Crea/actualiza Muestra(codigo_barra, tipo) y marca etiqueta_impresa=True.
    Devuelve los bytes del PDF (cada etiqueta en una página 70x30 mm).
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape

    paciente = orden.paciente
    fecha_str = orden.fecha.strftime("%d/%m/%Y")
    sexo = (paciente.sexo or '').upper()[:1] if hasattr(paciente, 'sexo') and paciente.sexo else ''
    doc = (paciente.documento_identidad or '').strip()

    # Construir lista de etiquetas
    etiquetas = []

    # 1) etiqueta general (sin sufijo)
    etiquetas.append({
        'code': orden.numero_orden,
        'linea_examen': 'ETIQUETA ORDEN'
    })

    # 2) etiquetas por examen (con sufijo .n)
    i = 1
    for oe in orden.examenes.select_related('examen').all():
        codigo = f"{orden.numero_orden}.{i}"
        etiquetas.append({
            'code': codigo,
            'linea_examen': (oe.examen.nombre or '').upper()[:30] if oe.examen else ''
        })
        # Crear/asegurar muestra
        try:
            Muestra.objects.get_or_create(
                orden=orden,
                codigo_barra=codigo,
                defaults={
                    'tipo': (oe.examen.muestra or 'Sangre') if oe.examen else 'Sangre',
                    'creado_por': user
                }
            )
        except Exception:
            pass
        i += 1

    # PDF: tamaño por etiqueta (70x30 mm)
    w, h = (70*mm, 30*mm)
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))

    for et in etiquetas:
        code = et['code']
        # Barcode Code128
        bc = code128.Code128(code, barHeight=12*mm, barWidth=0.38)
        # Centrados
        x_center = w/2.0
        # Dibuja barcode
        bw = bc.width
        bc.drawOn(c, x_center - (bw/2.0), h - 16*mm)

        # código impreso debajo del barcode
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x_center, h - 17.5*mm, code)

        # Nombre paciente
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(2*mm, h - 21*mm, (paciente.nombre_completo or '').upper()[:36])

        # Doc, sexo, fecha
        c.setFont("Helvetica", 7)
        linea_info = f"{doc or ''}   {sexo or ''}   {fecha_str}"
        c.drawString(2*mm, h - 25*mm, linea_info.strip())

        # Línea examen
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(2*mm, h - 29*mm, (et['linea_examen'] or '').upper())

        c.showPage()

    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()

    # Marcar muestras como impresas
    try:
        Muestra.objects.filter(orden=orden, codigo_barra__startswith=orden.numero_orden).update(etiqueta_impresa=True)
    except Exception:
        pass

    return pdf_bytes


@login_required
def orden_etiquetas_pdf(request, orden_id):
    """
    Etiquetas tamaño real: 54.7 x 25.0 mm (155 x 71 pt). 1 etiqueta = 1 página.
    Estructura: TÍTULO → BARRAS → NÚM. → NOMBRE → DOC/SEXO/FECHA ... SUFIJO(4) → DETALLE
    Sin solapes y respetando márgenes.
    """
    from io import BytesIO
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from reportlab.pdfgen import canvas
    from reportlab.graphics.barcode import code128
    from reportlab.lib.units import mm

    # ===== Datos base =====
    orden = get_object_or_404(
        Orden.objects.select_related('paciente').prefetch_related('examenes__examen'),
        id=orden_id
    )
    p = orden.paciente
    nombre = (p.nombre_completo or "").upper()
    doc    = (p.documento_identidad or "")
    sexo   = ((p.sexo or "").strip()[:1] or "-").upper()

    def fmt_fecha(dt):
        if not dt: return ""
        return (timezone.localtime(dt) if timezone.is_aware(dt) else dt).strftime("%d/%m/%Y")

    fecha_str = fmt_fecha(orden.fecha)

    def six(num):
        try:
            return f"{int(num):06d}"
        except Exception:
            d = ''.join(ch for ch in str(num) if ch.isdigit()) or "0"
            return d[-6:].rjust(6, "0")

    base_code = six(orden.numero_orden)   # p. ej. 001234
    sufijo4   = base_code[-4:]

    # Primera etiqueta (pedido médico) + una por examen
    etiquetas = [("PEDIDO MEDICO", base_code, "ETIQUETA ORDEN")]
    sec = 1
    for oe in orden.examenes.select_related('examen'):
        ex = oe.examen
        titulo  = (ex.muestra or ex.nombre or "MUESTRA").strip().upper()
        detalle = (ex.area or ex.nombre or "").strip().upper()
        etiquetas.append((titulo, f"{base_code}.{sec}", detalle))
        sec += 1

    # ===== Tamaño exacto etiqueta =====
    W = 54.7 * mm
    H = 25.0 * mm

    # Márgenes y tamaños (ajustados para que TODO quepa)
    M_LEFT, M_RIGHT, M_TOP, M_BOTTOM = 1*mm, 1*mm, 0.5*mm, 1.5*mm

    FS_TITLE   = 8.0   # título
    FS_NAME    = 7.0   # nombre
    FS_LINE    = 6.2   # doc/sexo/fecha y sufijo
    FS_DETAIL  = 6.8   # detalle
    FS_READ    = 7.0   # número legible bajo barras

    BAR_H      = 5.7*mm
    BAR_W      = 0.33*mm

    GAP_T2BAR  = 1.4*mm     # título → barras
    GAP_BAR2N  = 1.2*mm     # barras → número legible
    GAP_N2NM   = 1.4*mm     # número legible → nombre
    GAP_NM2LN  = 1.2*mm     # nombre → doc/sexo/fecha
    GAP_LN2DT  = 1.0*mm     # línea → detalle

    def fit_line(c, text, font, size, maxw):
        c.setFont(font, size)
        if c.stringWidth(text, font, size) <= maxw:
            return text
        ell = "…"
        ell_w = c.stringWidth(ell, font, size)
        t = text
        while t and c.stringWidth(t, font, size) + ell_w > maxw:
            t = t[:-1]
        return t + ell

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))

    for titulo, code_value, detalle in etiquetas:
        c.setPageSize((W, H))
        left, right = M_LEFT, W - M_RIGHT
        maxw = right - left

        # Comenzamos desde arriba y bajamos
        y = H - M_TOP

        # 1) Título
        c.setFont("Helvetica-Bold", FS_TITLE)
        y -= FS_TITLE
        c.drawString(left, y, fit_line(c, titulo, "Helvetica-Bold", FS_TITLE, maxw))
        y -= GAP_T2BAR

        # 2) Código de barras (centrado). Lo “anclamos” con su parte superior en y_top
        y_top = y
        barcode = code128.Code128(code_value, barWidth=BAR_W, barHeight=BAR_H, humanReadable=False)
        bx = (W - barcode.width) / 2.0
        by = y_top - BAR_H
        barcode.drawOn(c, bx, by)

        # 3) Número legible bajo barras
        y = by - GAP_BAR2N
        c.setFont("Helvetica-Bold", FS_READ)
        y -= FS_READ
        c.drawCentredString(W/2.0, y, code_value)

        # 4) Nombre
        y -= GAP_N2NM
        c.setFont("Helvetica-Bold", FS_NAME)
        y -= FS_NAME
        c.drawString(left, y, fit_line(c, nombre, "Helvetica-Bold", FS_NAME, maxw))

        # 5) DOC  SEXO  FECHA ................ SUFIJO(4)
        y -= GAP_NM2LN
        c.setFont("Helvetica", FS_LINE)
        linea_left = f"{doc}  {sexo}  {fecha_str}"
        # Reservamos espacio a la derecha para el sufijo
        y -= FS_LINE
        suf = sufijo4
        # texto izquierda ajustado
        reserva = c.stringWidth("   " + suf, "Helvetica-Bold", FS_LINE)
        c.drawString(left, y, fit_line(c, linea_left, "Helvetica", FS_LINE, maxw - reserva))
        # sufijo a la derecha
        c.setFont("Helvetica-Bold", FS_LINE)
        c.drawRightString(right, y, suf)

        # 6) Detalle (última línea antes del margen inferior)
        y -= GAP_LN2DT
        c.setFont("Helvetica-Bold", FS_DETAIL)
        y = max(y - FS_DETAIL, M_BOTTOM)  # nunca pisa el margen inferior
        c.drawString(left, y, fit_line(c, (detalle or "").upper(), "Helvetica-Bold", FS_DETAIL, maxw))

        c.showPage()

    c.save()
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type="application/pdf")



@login_required
def detalle_orden(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    examenes = orden.examenes.all()
    return render(request, 'laboratorio/detalle_orden.html', {'orden': orden, 'examenes': examenes})


@login_required
def resultados_orden(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    examenes = orden.examenes.select_related('examen').prefetch_related('resultados')
    return render(request, 'laboratorio/resultados.html', {
        'orden': orden,
        'examenes': examenes
    })

@login_required
def orden_pdf(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"ORDEN: {orden.numero_orden}")
    p.drawString(100, 735, f"PACIENTE: {orden.paciente.nombre_completo}")
    p.drawString(100, 720, f"DOCUMENTO: {orden.paciente.documento_identidad}")
    y = 700
    for e in orden.examenes.all():
        p.drawString(100, y, f"- {e.examen.nombre}")
        y -= 15
    p.showPage()
    p.save()
    buffer.seek(0)
    return HttpResponse(buffer.getvalue(), content_type='application/pdf')


# ------------------------------
# Pacientes (AJAX) (TU CÓDIGO ORIGINAL) — (ARREGLADO SOLO SINTAXIS)
# ------------------------------

@login_required
def paciente_nuevo_ajax(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    doc = request.POST.get('documento_identidad', '').strip()
    nombres = request.POST.get('nombres', '').strip()
    apellidos = request.POST.get('apellidos', '').strip()
    nombre_completo = f"{nombres} {apellidos}".strip()
    sexo = request.POST.get('sexo')
    fecha_nacimiento = request.POST.get('fecha_nacimiento') or None
    telefono = request.POST.get('telefono') or None
    email = request.POST.get('email') or None
    direccion = request.POST.get('direccion') or None

    if not doc or not nombre_completo:
        return JsonResponse({'status': 'error', 'message': 'Documento y nombre son obligatorios'}, status=400)

    p, created = Paciente.objects.get_or_create(
        documento_identidad=doc,
        defaults={
            'nombre_completo': nombre_completo,
            'sexo': sexo or 'M',
            'fecha_nacimiento': fecha_nacimiento,
            'telefono': telefono,
            'email': email,
            'direccion': direccion,
            'fecha_registro': date.today(),
            'creado_por': request.user
        }
    )

    if not created:
        changed = False
        if sexo and p.sexo != sexo:
            p.sexo = sexo; changed = True
        if fecha_nacimiento and p.fecha_nacimiento != fecha_nacimiento:
            p.fecha_nacimiento = fecha_nacimiento; changed = True
        if telefono and p.telefono != telefono:
            p.telefono = telefono; changed = True
        if email and p.email != email:
            p.email = email; changed = True
        if direccion and p.direccion != direccion:
            p.direccion = direccion; changed = True
        if changed:
            p.modificado_por = request.user
            p.save()

    return JsonResponse({
        'status': 'ok',
        'paciente': {
            'id': p.id,
            'documento_identidad': p.documento_identidad,
            'nombre_completo': p.nombre_completo,
        }
    })


@login_required
def buscar_paciente_ajax(request):
    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    doc = request.GET.get('documento_identidad', '').strip()
    if not doc:
        return JsonResponse({'status': 'error', 'message': 'Documento vacío'}, status=400)

    try:
        p = Paciente.objects.get(documento_identidad=doc)
        return JsonResponse({
            'status': 'ok',
            'paciente': {
                'id': p.id,
                'documento_identidad': p.documento_identidad,
                'nombre_completo': p.nombre_completo,
            }
        })
    except Paciente.DoesNotExist:
        return JsonResponse({'status': 'not_found', 'message': 'Paciente no registrado'})


# ------------------------------
# Catálogo (TU CÓDIGO ORIGINAL)
# ------------------------------

@login_required
def catalogo_examenes(request):
    examenes_list = Examen.objects.all().order_by('area', 'nombre')
    query = request.GET.get('q', '').strip()
    if query:
        examenes_list = examenes_list.filter(nombre__icontains=query) | examenes_list.filter(codigo__icontains=query)
    paginator = Paginator(examenes_list, 15)
    page_number = request.GET.get('page')
    examenes = paginator.get_page(page_number)
    return render(request, 'laboratorio/catalogo.html', {'examenes': examenes, 'query': query})


@login_required
def catalogo_importar_excel(request):
    if request.method == 'POST' and request.FILES.get('archivo'):
        file = request.FILES['archivo']
        path = default_storage.save(f"tmp/{file.name}", file)
        full_path = default_storage.path(path)
        df = pd.read_excel(full_path)
        for _, row in df.iterrows():
            Examen.objects.update_or_create(
                codigo=str(row['Código']).strip(),
                defaults={
                    'nombre': str(row['Nombre']).strip(),
                    'area': str(row['Área']).strip(),
                    'precio': float(row['Precio']),
                    'muestra': str(row.get('Tipo de Muestra', '')).strip() if 'Tipo de Muestra' in row else '',
                    'creado_por': request.user,
                }
            )
        default_storage.delete(path)
        messages.success(request, "Archivo importado correctamente.")
        return redirect('catalogo_examenes')
    return redirect('catalogo_examenes')


@login_required
def catalogo_editar_ajax(request, examen_id):
    examen = get_object_or_404(Examen, id=examen_id)
    if request.method == 'POST':
        examen.codigo = request.POST.get('codigo', examen.codigo)
        examen.nombre = request.POST.get('nombre', examen.nombre)
        examen.area = request.POST.get('area', examen.area)
        examen.muestra = request.POST.get('muestra', examen.muestra)
        examen.precio = request.POST.get('precio', examen.precio)
        examen.modificado_por = request.user
        examen.save()
        return JsonResponse({'status': 'ok', 'message': 'Examen actualizado correctamente'})
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


@login_required
def catalogo_eliminar_ajax(request, examen_id):
    if request.method == 'POST':
        examen = get_object_or_404(Examen, id=examen_id)
        examen.delete()
        return JsonResponse({'status': 'ok', 'message': 'Examen eliminado correctamente'})
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


@login_required
def catalogo_eliminar_todos_ajax(request):
    if request.method == 'POST':
        Examen.objects.all().delete()
        return JsonResponse({'status': 'ok', 'message': 'Todos los exámenes fueron eliminados correctamente'})
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@login_required
def catalogo_exportar(request):
    examenes = Examen.objects.all().values('codigo', 'nombre', 'area', 'muestra', 'precio')
    if not examenes:
        return HttpResponse("No hay datos para exportar.", content_type="text/plain")

    df = pd.DataFrame(list(examenes))
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=catalogo_principal.xlsx'
    df.to_excel(response, index=False)
    response['Content-Disposition'] = 'attachment; filename=catalogo_principal.xlsx'
    return response



# ------------------------------
# Buscador global (TU CÓDIGO ORIGINAL)
# ------------------------------

@login_required
def buscar_examenes_ajax(request):
    query = request.GET.get('q', '').strip()
    resultados = []
    if query:
        examenes = Examen.objects.filter(nombre__icontains=query) | Examen.objects.filter(codigo__icontains=query)
        examenes = examenes.order_by('area', 'nombre')[:20]
        resultados = [
            {
                'id': e.id,
                'codigo': e.codigo,
                'nombre': e.nombre,
                'area': e.area,
                'precio': float(e.precio),
                'muestra': e.muestra or '',
            }
            for e in examenes
        ]
    return JsonResponse({'status': 'ok', 'resultados': resultados})


# ------------------------------
# RESULTADOS (AJAX): burbuja / resumen / guardar (NUEVO, SIN ROMPER LO EXISTENTE)
# ------------------------------

@login_required
@require_http_methods(["GET"])
def burbuja_resultado_ajax(request):
    oe_id = request.GET.get('orden_examen_id')
    if not oe_id:
        return JsonResponse({'status': 'error', 'message': 'Falta parámetro orden_examen_id'}, status=400)

    orden_examen = get_object_or_404(
        OrdenExamen.objects.select_related('orden', 'examen'),
        id=oe_id
    )
    resultados = Resultado.objects.filter(orden_examen=orden_examen).order_by('id')

    ctx = {
        'orden_examen': orden_examen,
        'examen': orden_examen.examen,
        'paciente': getattr(orden_examen.orden, 'paciente', None),
        'resultados': resultados,
    }
    html = render_to_string('laboratorio/partials/burbuja_resultado.html', context=ctx, request=request)
    return JsonResponse({'status': 'ok', 'html': html})


@login_required
@csrf_exempt
def guardar_resultados_ajax(request):
    """
    Versión blindada definitiva:
    - Nunca redirige por 'Guardar'.
    - Solo redirige si el POST trae exactamente 'accion': 'enviar_validacion'.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))

        resultado_id = data.get('id')
        valor = (data.get('valor') or '').strip()
        unidad = data.get('unidad')
        referencia = data.get('referencia')
        metodo = data.get('metodo')
        observacion = data.get('observacion')
        accion = str(data.get('accion') or '').lower().strip()  # <--- clave

        # Actualiza siempre el resultado
        res = Resultado.objects.select_related('orden_examen__orden').get(id=resultado_id)
        res.valor = valor
        res.unidad = unidad
        res.referencia = referencia
        res.metodo = metodo
        res.observacion = observacion
        if hasattr(res, 'marca_fuera_de_rango'):
            try:
                res.marca_fuera_de_rango()
            except Exception:
                pass
        res.save()

        # Solo cambia estado y redirige si la acción fue 'enviar_validacion'
        if accion == 'enviar_validacion':
            oe = res.orden_examen
            orden = oe.orden
            oe.estado = "En validación"
            oe.save(update_fields=['estado'])
            if not orden.examenes.filter(estado__in=["Pendiente", "En proceso"]).exists():
                orden.estado = "En validación"
                orden.save(update_fields=['estado'])
            return JsonResponse({'status': 'redirect', 'redirect_url': '/laboratorio/resultados_home/'})

        # Cualquier otra acción (guardar, etc.) se queda en la pantalla
        return JsonResponse({'status': 'ok', 'message': 'Cambios guardados correctamente.'})

    except Resultado.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Resultado no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)







# ------------------------------
# Home del módulo Resultados (NUEVO: acceso directo navegable)
# ------------------------------
@login_required
def resultados_home(request):
    """
    Entrada al módulo 'Resultados'.
    - ?orden_id=XX -> redirige a /ordenes/XX/resultados/
    - Sin parámetro: lista las últimas 20 órdenes con links a resultados.
    """
    orden_id = request.GET.get('orden_id')
    if (orden_id):
        return redirect('resultados_orden', orden_id=orden_id)

    ordenes = Orden.objects.all().order_by('-fecha')[:20]
    try:
        return render(request, 'laboratorio/resultados_home.html', {'ordenes': ordenes})
    except TemplateDoesNotExist:
        items = []
        for o in ordenes:
            items.append(
                f'<li>Orden {o.numero_orden} — {o.paciente.nombre_completo} '
                f'(<a href="/ordenes/{o.id}/resultados/">ver resultados</a>)</li>'
            )
        html = (
            '<h2>Módulo de Resultados</h2>'
            '<p>Selecciona una orden para ver sus resultados:</p>'
            f'<ul>{"".join(items) or "<li>No hay órdenes recientes.</li>"}</ul>'
        )
        return HttpResponse(html)


# ------------------------------
# NUEVA VISTA (AGREGADA SIN MODIFICAR NADA MÁS)
# ------------------------------
@login_required
def resultados_lista(request):
    # import local para no tocar encabezados existentes
    from django.db.models import Q

    q = (request.GET.get('q') or '').strip()

    ordenes = (
        Orden.objects
        .filter(examenes__estado__in=['Pendiente', 'En proceso'])
        .select_related('paciente')
        .distinct()
        .order_by('-fecha')
    )

    if q:
        ordenes = ordenes.filter(
            Q(paciente__nombre_completo__icontains=q) |
            Q(paciente__documento_identidad__icontains=q) |
            Q(numero_orden__icontains=q)
        )

    return render(request, 'laboratorio/resultados_lista.html', {
        'ordenes': ordenes,
        'query': q,
    })



@login_required
def catalogo_tecnico(request):
    """
    Lista con búsqueda y paginación del Catálogo Técnico (ExamenParametro).
    """
    q = (request.GET.get('q') or '').strip()
    qs = ExamenParametro.objects.select_related('examen').all()
    if q:
        qs = qs.filter(
            Q(examen__codigo__icontains=q)|
            Q(examen__nombre__icontains=q)|
            Q(nombre__icontains=q)|
            Q(unidad__icontains=q)|
            Q(referencia__icontains=q)|
            Q(metodo__icontains=q)
        )
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'laboratorio/catalogo_tecnico.html', {'page_obj': page_obj, 'query': q})

@login_required
@require_http_methods(["POST"])
def catalogo_tecnico_save(request):
    """
    Guarda edición inline de un parámetro existente (vía FormData).
    """
    try:
        id = request.POST.get('id')
        p = ExamenParametro.objects.select_related('examen').get(id=id)

        p.nombre = request.POST.get('nombre') or p.nombre
        p.unidad = request.POST.get('unidad')
        p.referencia = request.POST.get('referencia')
        p.metodo = request.POST.get('metodo')
        p.observacion = request.POST.get('observacion')
        p.acreditado = request.POST.get('acreditado') == 'true'
        p.save()

        return JsonResponse({'status': 'ok'})
    except ExamenParametro.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Parámetro no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def catalogo_tecnico_toggle_acreditado(request):
    """
    Alterna acreditación (✔/✖).
    """
    try:
        p = ExamenParametro.objects.get(id=request.POST.get('id'))
        p.acreditado = not p.acreditado
        p.save()
        return JsonResponse({'status':'ok','acreditado': p.acreditado})
    except ExamenParametro.DoesNotExist:
        return JsonResponse({'status':'error','message':'Parámetro no encontrado.'}, status=404)

@login_required
@require_http_methods(["POST"])
def catalogo_tecnico_delete(request):
    """
    Elimina un parámetro.
    """
    try:
        p = ExamenParametro.objects.get(id=request.POST.get('id'))
        p.delete()
        return JsonResponse({'status':'ok'})
    except ExamenParametro.DoesNotExist:
        return JsonResponse({'status':'error','message':'Parámetro no encontrado.'}, status=404)

@login_required
@require_http_methods(["POST"])
def catalogo_tecnico_create(request):
    """
    Crea un nuevo parámetro:
    - examen_busqueda: código o nombre del examen (se prioriza código).
    - nombre, unidad, referencia, metodo, observacion, acreditado
    """
    examen_q = (request.POST.get('examen_busqueda') or '').strip()
    if not examen_q:
        return JsonResponse({'status':'error','message':'Ingrese el examen (código o nombre).'}, status=400)

    # Resolver examen por código o por nombre (prioridad: código)
    ex = Examen.objects.filter(codigo__iexact=examen_q).first()
    if not ex:
        ex = Examen.objects.filter(nombre__iexact=examen_q).first()
    if not ex:
        return JsonResponse({'status':'error','message':'Examen no encontrado por código o nombre.'}, status=404)

    nombre = (request.POST.get('nombre') or '').strip()
    if not nombre:
        return JsonResponse({'status':'error','message':'El nombre del parámetro es obligatorio.'}, status=400)

    # Evitar duplicados (mismo examen + mismo nombre)
    if ExamenParametro.objects.filter(examen=ex, nombre__iexact=nombre).exists():
        return JsonResponse({'status':'error','message':'Ya existe un parámetro con ese nombre para este examen.'}, status=409)

    p = ExamenParametro.objects.create(
        examen = ex,
        nombre = nombre,
        unidad = request.POST.get('unidad') or None,
        referencia = request.POST.get('referencia') or None,
        metodo = request.POST.get('metodo') or None,
        observacion = request.POST.get('observacion') or None,
        acreditado = True if request.POST.get('acreditado') in ['on','true','1'] else False
    )
    return JsonResponse({'status':'ok','id':p.id})

@login_required
@require_http_methods(["POST"])
def catalogo_tecnico_import(request):
    """
    Importa parámetros desde Excel/CSV.
    Encabezados esperados:
      codigo_examen, parametro, unidad, referencia, metodo, observacion, acreditado
    """
    f = request.FILES.get('archivo')
    if not f:
        return JsonResponse({'status':'error','message':'Adjunta un archivo .xlsx o .csv'}, status=400)

    created, updated, skipped = 0, 0, 0

    def upsert_row(row):
        nonlocal created, updated, skipped
        code = (str(row.get('codigo_examen') or '').strip())
        param = (str(row.get('parametro') or '').strip())
        if not code or not param:
            skipped += 1; return
        ex = Examen.objects.filter(codigo__iexact=code).first()
        if not ex:
            skipped += 1; return
        unidad = str(row.get('unidad') or '').strip() or None
        ref = str(row.get('referencia') or '').strip() or None
        metodo = str(row.get('metodo') or '').strip() or None
        obs = str(row.get('observacion') or '').strip() or None
        acreditado_val = str(row.get('acreditado') or '').strip().lower()
        acreditado = True if acreditado_val in ['1','true','si','sí','yes','y','x','ok'] else False

        obj, was_created = ExamenParametro.objects.update_or_create(
            examen=ex, nombre__iexact=param,
            defaults={'nombre':param,'unidad':unidad,'referencia':ref,'metodo':metodo,'observacion':obs,'acreditado':acreditado}
        )
        if was_created: created += 1
        else: updated += 1

    try:
        name = f.name.lower()
        if name.endswith('.csv'):
            data = f.read().decode('utf-8', errors='ignore')
            reader = csv.DictReader(io.StringIO(data))
            for row in reader: upsert_row(row)
        else:
            if pd is None:
                return JsonResponse({'status':'error','message':'Pandas no disponible para Excel. Usa CSV o instala pandas.'}, status=400)
            df = pd.read_excel(f)
            for _, row in df.iterrows():
                upsert_row(row.to_dict())
        return JsonResponse({'status':'ok','message':f'Importación OK: {created} nuevos, {updated} actualizados, {skipped} omitidos.'})
    except Exception as e:
        return JsonResponse({'status':'error','message':str(e)}, status=500)

@login_required
def catalogo_tecnico_export(request):
    """
    Exporta Catálogo Técnico en Excel (.xlsx).
    Respeta el filtro actual (?q=).
    """
    q = (request.GET.get('q') or '').strip()
    qs = ExamenParametro.objects.select_related('examen').all()

    if q:
        qs = qs.filter(
            Q(examen__codigo__icontains=q) |
            Q(examen__nombre__icontains=q) |
            Q(nombre__icontains=q) |
            Q(unidad__icontains=q) |
            Q(referencia__icontains=q) |
            Q(metodo__icontains=q)
        )

    # Preparar DataFrame
    datos = []
    for p in qs:
        datos.append({
            'Código Examen': p.examen.codigo,
            'Examen': p.examen.nombre,
            'Parámetro': p.nombre,
            'Unidad': p.unidad or '',
            'Referencia': p.referencia or '',
            'Método': p.metodo or '',
            'Observación': p.observacion or '',
            'Acreditado': 'Sí' if p.acreditado else 'No',
        })

    df = pd.DataFrame(datos)

    # Respuesta tipo Excel
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=catalogo_tecnico.xlsx'

    # Exportar usando pandas (openpyxl)
    df.to_excel(response, index=False)

    return response


    # ------------------------------
# MÓDULO DE VALIDACIÓN (DESDE CERO)
# ------------------------------
from django.views.decorators.http import require_http_methods

@login_required
def validacion_lista(request):
    """
    Lista de órdenes candidatas a validación.
    Criterio:
      - Órdenes que tengan al menos un OrdenExamen en 'En validación', o
      - Órdenes que no tengan OrdenExamen en 'Pendiente' o 'En proceso',
        y que NO estén todavía 'Validado'.
    """
    ordenes = (
        Orden.objects
        .select_related('paciente')
        .prefetch_related('examenes__examen', 'examenes__resultados')
        .order_by('-fecha')
    )

    candidatas = []
    for o in ordenes:
        estados_oe = [(oe.estado or '').strip() for oe in o.examenes.all()]
        tiene_en_validacion = any(s == 'En validación' for s in estados_oe)
        sin_pendientes = not any(s in ['Pendiente', 'En proceso'] for s in estados_oe)
        if tiene_en_validacion or (sin_pendientes and (o.estado or '') != 'Validado'):
            candidatas.append(o)

    return render(request, 'laboratorio/validacion_lista.html', {
        'ordenes': candidatas
    })


@login_required
@require_http_methods(["POST"])
def validar_parametro_ajax(request, resultado_id):
    """
    Valida un parámetro (Resultado).
    Si todos los resultados del OrdenExamen quedan validados -> OrdenExamen.estado = 'Validado'.
    Si todos los OrdenExamen de la Orden quedan 'Validado' -> Orden.estado = 'Validado'.
    """
    try:
        r = Resultado.objects.select_related('orden_examen__orden').get(id=resultado_id)
    except Resultado.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Resultado no encontrado.'}, status=404)

    r.validado = True
    r.validado_por = request.user
    r.fecha_validacion = timezone.now()
    r.save(update_fields=['validado', 'validado_por', 'fecha_validacion'])

    oe = r.orden_examen
    # ¿Todos los resultados del OE validados?
    if not oe.resultados.filter(validado=False).exists():
        if (oe.estado or '') != 'Validado':
            oe.estado = 'Validado'
            oe.save(update_fields=['estado'])

    # ¿Toda la orden validada?
    orden = oe.orden
    if not orden.examenes.filter(estado__in=['Pendiente', 'En proceso', 'Procesado', 'En validación']).exists():
        if (orden.estado or '') != 'Validado':
            orden.estado = 'Validado'
            orden.save(update_fields=['estado'])

    return JsonResponse({'status': 'ok'})


@login_required
@require_http_methods(["POST"])
def anular_parametro_ajax(request, resultado_id):
    """
    Anula la validación de un parámetro.
    El OrdenExamen vuelve a 'En validación'.
    La Orden, si estaba 'Validado', pasa a 'En validación'.
    """
    try:
        r = Resultado.objects.select_related('orden_examen__orden').get(id=resultado_id)
    except Resultado.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Resultado no encontrado.'}, status=404)

    r.validado = False
    r.validado_por = None
    r.fecha_validacion = None
    r.save(update_fields=['validado', 'validado_por', 'fecha_validacion'])

    oe = r.orden_examen
    if (oe.estado or '') != 'En validación':
        oe.estado = 'En validación'
        oe.save(update_fields=['estado'])

    orden = oe.orden
    if (orden.estado or '') == 'Validado':
        orden.estado = 'En validación'
        orden.save(update_fields=['estado'])

    return JsonResponse({'status': 'ok'})


@login_required
@require_http_methods(["POST"])
def devolver_a_resultados_ajax(request, orden_id):
    """
    Devuelve la ORDEN a resultados:
      - Todo OrdenExamen con resultados no validados -> 'En proceso'
      - La Orden -> 'En proceso'
    """
    try:
        orden = Orden.objects.prefetch_related('examenes__resultados').get(id=orden_id)
    except Orden.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Orden no encontrada.'}, status=404)

    for oe in orden.examenes.all():
        # Si tiene algún resultado no validado, lo regresamos a 'En proceso'
        if oe.resultados.filter(validado=False).exists():
            if (oe.estado or '') != 'En proceso':
                oe.estado = 'En proceso'
                oe.save(update_fields=['estado'])

    if (orden.estado or '') != 'En proceso':
        orden.estado = 'En proceso'
        orden.save(update_fields=['estado'])

    return JsonResponse({'status': 'ok'})


@login_required
@require_http_methods(["POST"])
def cerrar_validacion_orden_ajax(request, orden_id):
    """
    Cierra la validación de la ORDEN:
      - Verifica que TODOS los Resultados estén validados.
      - Si algo no está validado -> 409.
      - Si todo ok: todos los OE = 'Validado' y Orden = 'Validado'.
    """
    try:
        orden = Orden.objects.prefetch_related('examenes__resultados').get(id=orden_id)
    except Orden.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Orden no encontrada.'}, status=404)

    # ¿Hay algún resultado sin validar?
    for oe in orden.examenes.all():
        if oe.resultados.filter(validado=False).exists():
            return JsonResponse({'status': 'error', 'message': 'Aún hay parámetros sin validar.'}, status=409)

    # Marca todos los OE como 'Validado'
    for oe in orden.examenes.all():
        if (oe.estado or '') != 'Validado':
            oe.estado = 'Validado'
            oe.save(update_fields=['estado'])

    # Marca la Orden como 'Validado'
    if (orden.estado or '') != 'Validado':
        orden.estado = 'Validado'
        orden.save(update_fields=['estado'])

    return JsonResponse({'status': 'ok'})
# --- AÑADIR AL FINAL DE views.py (sin mover nada de arriba) ---
@login_required
@require_http_methods(["GET"])
def validacion_modal_html(request, orden_id):
    """
    Devuelve HTML (como JSON) para poblar el modal de validación
    sin usar un template separado (cumple: el modal vive en la misma página).
    """
    try:
        orden = (
            Orden.objects
            .select_related('paciente')
            .prefetch_related('examenes__examen', 'examenes__resultados')
            .get(id=orden_id)
        )
    except Orden.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Orden no encontrada.'}, status=404)

    # Construcción de HTML simple: encabezado + lista de parámetros con botones
    parts = []
    parts.append(f'''
      <div class="small" style="margin-bottom:8px;">
        <div><strong>Orden:</strong> {orden.numero_orden}</div>
        <div><strong>Paciente:</strong> {orden.paciente.nombre_completo} — {orden.paciente.documento_identidad}</div>
        <div><strong>Fecha:</strong> {orden.fecha.strftime("%d/%m/%Y %H:%M")}</div>
        <div><strong>Estado:</strong> <span class="badge">{orden.estado or ""}</span></div>
      </div>
      <div style="max-height:60vh;overflow:auto;border:1px solid #e5e7eb;border-radius:8px;padding:8px;">
    ''')

    for oe in orden.examenes.all():
        parts.append(f'''
          <div style="margin:8px 0 6px 0;font-weight:700;">
            {oe.examen.nombre} <span class="badge">{oe.examen.codigo}</span>
            <span class="badge">{oe.estado or ""}</span>
          </div>
        ''')
        if oe.resultados.exists():
            for r in oe.resultados.all():
                ver_btn = (f'<button type="button" class="btn green btn-validar" data-id="{r.id}">Validar</button>') if not r.validado else ''
                anu_btn = (f'<button type="button" class="btn gray btn-anular" data-id="{r.id}">Anular</button>') if r.validado else ''
                unidad = f'<span class="badge">{r.unidad}</span>' if r.unidad else ''
                ref = f'<span class="badge">{r.referencia}</span>' if r.referencia else ''
                met = f'<span class="badge">{r.metodo}</span>' if r.metodo else ''
                obs = f'<span class="badge">{r.observacion}</span>' if r.observacion else ''
                val_tag = '<span class="badge" style="border-color:#34d399;background:#ecfdf5;color:#065f46;">✓ Validado</span>' if r.validado else '<span class="badge">Pendiente</span>'

                parts.append(f'''
                  <div class="meta" data-rid="{r.id}" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0;">
                    <span>{r.parametro} = <strong>{(r.valor or "")}</strong></span>
                    {unidad}{ref}{met}{obs}{val_tag}
                    {ver_btn}{anu_btn}
                  </div>
                ''')
        else:
            parts.append('<div class="meta">Sin resultados en este examen.</div>')

    # Acciones de orden (todas dentro del modal)
    parts.append(f'''
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
        <button type="button" class="btn red" id="btnDevolverOrden" data-orden="{orden.id}">Devolver a resultados</button>
        <button type="button" class="btn green" id="btnCerrarValidacion" data-orden="{orden.id}">Cerrar validación</button>
      </div>
    ''')

    html = ''.join(parts)
    return JsonResponse({'status': 'ok', 'html': html})


@login_required
def pacientes_lista(request):
    """
    Muestra todos los pacientes registrados en el sistema (solo lectura).
    """
    from django.utils import timezone
    from datetime import timedelta
    
    pacientes = Paciente.objects.all().order_by("-creado_en")
    
    # KPIs para el dashboard
    total_pacientes = Paciente.objects.count()
    
    # Pacientes nuevos este mes
    ahora = timezone.now()
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nuevos_mes = Paciente.objects.filter(creado_en__gte=inicio_mes).count()
    
    # Órdenes pendientes (estado Pendiente o En proceso)
    ordenes_pendientes = Orden.objects.filter(estado__in=['Pendiente', 'En proceso']).count()
    
    # Resultados pendientes: OrdenExamen con estado Pendiente que tienen resultados pendientes de validar
    from django.db.models import Count
    resultados_pendientes = OrdenExamen.objects.filter(
        estado='Pendiente'
    ).exclude(
        resultados__isnull=False
    ).count()
    # También contar los que tienen resultados pero no validados
    resultados_sin_validar = Resultado.objects.filter(validado=False).count()
    resultados_pendientes = max(resultados_pendientes, resultados_sin_validar)
    
    return render(request, "laboratorio/pacientes_lista.html", {
        "pacientes": pacientes,
        "total_pacientes": total_pacientes,
        "nuevos_mes": nuevos_mes,
        "ordenes_pendientes": ordenes_pendientes,
        "resultados_pendientes": resultados_pendientes,
    })

@login_required
@require_http_methods(["GET"])
def paciente_editar_ajax(request, paciente_id):
    """
    Devuelve los datos del paciente en formato JSON para precargar la burbuja de edición.
    """
    try:
        paciente = Paciente.objects.get(id=paciente_id)
        data = model_to_dict(paciente, fields=[
            "documento_identidad", "nombre_completo", "sexo",
            "fecha_nacimiento", "telefono", "email", "direccion"
        ])
        if data.get("fecha_nacimiento"):
            data["fecha_nacimiento"] = paciente.fecha_nacimiento.strftime("%Y-%m-%d")
        return JsonResponse({"status": "ok", "paciente": data})
    except Paciente.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Paciente no encontrado"})


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def paciente_actualizar_ajax(request, paciente_id):
    """
    Actualiza los datos de un paciente desde la burbuja.
    """
    try:
        paciente = Paciente.objects.get(id=paciente_id)
    except Paciente.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Paciente no encontrado"})

    campos = [
        "documento_identidad", "nombre_completo", "sexo",
        "fecha_nacimiento", "telefono", "email", "direccion"
    ]
    for campo in campos:
        valor = request.POST.get(campo)
        if valor is not None:
            setattr(paciente, campo, valor)

    if hasattr(paciente, "modificado_por") and request.user.is_authenticated:
        paciente.modificado_por = request.user

    paciente.save()
    return JsonResponse({"status": "ok", "message": "Paciente actualizado correctamente"})

@login_required
@require_http_methods(["POST"])
def paciente_eliminar(request, paciente_id):
    paciente = get_object_or_404(Paciente, id=paciente_id)
    paciente.delete()
    return redirect("pacientes_lista")


# ------------------------------
# INFORME DE RESULTADOS (NUEVO)
# ------------------------------
@login_required
def informe_resultados(request, orden_id):
    orden = get_object_or_404(
        Orden.objects.select_related('paciente')
                     .prefetch_related('examenes__examen', 'examenes__resultados'),
        id=orden_id
    )

    if orden.estado != "Validado":
        return HttpResponseForbidden("El informe solo está disponible cuando la orden está Validada.")

    return render(request, "laboratorio/informe_resultados.html", {
        "orden": orden,
        "paciente": orden.paciente,
        "examenes": orden.examenes.all(),
        "fecha_informe": timezone.now(),
        "usuario_emisor": request.user,
    })
def calculate_age(birth_date):
    # ... (código de calculate_age) ...
    today = date.today()
    if isinstance(birth_date, date):
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return None

@login_required
def informe_resultados_pdf(request, orden_id):
    """
    Genera el informe de resultados en PDF usando WeasyPrint.
    Agrupa por AREA (campo Examen.area) usando la misma estructura que la vista resultados_orden.
    """
    orden = get_object_or_404(
        Orden.objects.select_related('paciente'),
        id=orden_id
    )

    # Solo permitir informe si la orden está validada
    if (orden.estado or "").strip() != "Validado":
        return HttpResponseForbidden("El informe solo está disponible cuando la orden está Validada.")

    # =========================
    # TOMAR EXÁMENES COMO EN resultados_orden
    # =========================
    examenes_oe = (
        orden.examenes  # related_name en OrdenExamen
        .select_related('examen')
        .prefetch_related('resultados')
        .all()
    )

    # =========================
    # AGRUPAR POR AREA Y EXAMEN
    # =========================
    grouped_data = defaultdict(lambda: defaultdict(list))

    for oe in examenes_oe:
        ex = oe.examen
        if not ex:
            continue

        area = (ex.area or "OTROS EXÁMENES").strip().upper()
        nombre_examen = (ex.nombre or "").strip().upper() or f"EXAMEN {ex.id}"

        for r in oe.resultados.all():
            grouped_data[area][nombre_examen].append(r)

    # Eliminar resultados duplicados: mantener solo el primero de cada parámetro único
    # Esto evita mostrar "Resultado generado" múltiples veces
    for area in grouped_data:
        for examen in grouped_data[area]:
            seen_params = set()
            unique_results = []
            for r in grouped_data[area][examen]:
                # Usar el ID del resultado como identificador único
                # Si el parámetro es igual, solo agregar uno
                param_key = (r.parametro, r.valor)
                if param_key not in seen_params:
                    seen_params.add(param_key)
                    unique_results.append(r)
            grouped_data[area][examen] = unique_results

    # Convertir defaultdict a dict regular para el template
    grouped_data = {k: dict(v) for k, v in grouped_data.items()}

    # =========================
    # VALIDADOR (último resultado validado)
    # =========================
    last_validated_result = (
        Resultado.objects
        .filter(orden_examen__orden=orden, validado=True)
        .select_related('validado_por')
        .order_by('-fecha_validacion')
        .first()
    )

    if last_validated_result and last_validated_result.validado_por:
        nombre_validador = (
            last_validated_result.validado_por.get_full_name()
            or last_validated_result.validado_por.username
        )
        fecha_validacion = last_validated_result.fecha_validacion
    else:
        nombre_validador = "PENDIENTE"
        fecha_validacion = None

    validador_data = {
        'nombre': nombre_validador,
        'fecha': fecha_validacion,
    }

    # =========================
    # EXTRAER DATOS DE GRÁFICAS (HISTOGRAMAS) DEL MENSAJE HL7
    # =========================
    import re
    import base64
    from io import BytesIO
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    def parse_histogram_binary(raw):
        """Extrae valores numéricos del formato histograma HL7."""
        if not raw:
            return None
        try:
            s = str(raw).strip()
            s = s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
            
            values_str = None
            if ";" in s:
                parts = s.split(";")
                if len(parts) >= 2:
                    values_str = parts[1]
            elif "," in s:
                parts = s.split(",")
                try:
                    first_val = int(parts[0])
                    if first_val > 65535:
                        values_str = ",".join(parts[1:])
                    else:
                        values_str = s
                except ValueError:
                    values_str = s
            else:
                return None
            
            if not values_str:
                return None
            
            values = []
            for x in values_str.split(","):
                x = x.strip()
                if x:
                    try:
                        values.append(int(x))
                    except:
                        try:
                            values.append(int(float(x)))
                        except:
                            continue
            
            return values if values else None
        except Exception:
            return None

    def generate_histogram_base64(values, label, x_max=None):
        """Genera un histograma como imagen base64."""
        if not values or len(values) < 2:
            return None
        try:
            fig, ax = plt.subplots(figsize=(6, 2), dpi=100)
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            
            x_vals = list(range(len(values)))
            ax.fill_between(x_vals, values, color='#00CCFF', alpha=0.7)
            ax.plot(x_vals, values, color='#0088CC', linewidth=0.8)
            
            ax.set_xlim(0, len(values) - 1)
            max_val = max(values) if values else 1
            ax.set_ylim(0, max_val * 1.1)
            
            ax.set_xticks([])
            ax.set_yticks([])
            
            ax.spines['left'].set_visible(True)
            ax.spines['left'].set_color('#333333')
            ax.spines['bottom'].set_visible(True)
            ax.spines['bottom'].set_color('#333333')
            ax.spines['right'].set_visible(False)
            ax.spines['top'].set_visible(False)
            
            ax.set_title(label, fontsize=9, fontweight='bold', pad=2)
            
            if label == "RBC":
                ax.set_xlim(0, 300)
                ax.set_xticks([0, 100, 200, 300])
                ax.set_xticklabels(['0', '100', '200', ''], fontsize=6)
                ax.set_xlabel('fL', fontsize=7)
            elif label == "PLT":
                ax.set_xlim(0, 40)
                ax.set_xticks([0, 10, 20, 30, 40])
                ax.set_xticklabels(['0', '10', '20', '30', '40'], fontsize=6)
                ax.set_xlabel('fL', fontsize=7)
            
            plt.tight_layout(pad=0.3)
            
            buf = BytesIO()
            plt.savefig(buf, format='png', transparent=True, dpi=100)
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            buf.close()
            
            return img_base64
        except Exception as e:
            print(f"Error generando histograma {label}: {e}")
            return None

    # Buscar mensaje HL7 con datos de histogramas
    graphs_data = {
        'rbc': None,
        'plt': None,
        'diff': None,
        'baso': None,
    }

    try:
        from configuracion.models import HL7Mensaje
        
        numero_orden = str(orden.numero_orden).strip()
        
        # Buscar mensaje que contenga histogramas (buscar por contenido específico)
        # El mensaje con histogramas es más antiguo, no el más reciente
        hl7_msg = None
        
        # Primero intentar buscar directamente por contenido de histograma
        hl7_msg = HL7Mensaje.objects.filter(
            sample_id=numero_orden,
            mensaje_raw__contains='RBC Histogram.Binary'
        ).order_by('id').first()
        
        # Si no encuentra, intentar con otras estrategias
        if not hl7_msg:
            candidates = [numero_orden, numero_orden.lstrip("0") or numero_orden, str(orden.id)]
            for candidate in candidates:
                msg = HL7Mensaje.objects.filter(
                    sample_id=candidate,
                    mensaje_raw__contains='RBC Histogram.Binary'
                ).order_by('id').first()
                if msg:
                    hl7_msg = msg
                    break
        
        if hl7_msg and hl7_msg.mensaje_raw:
            lines = hl7_msg.mensaje_raw.replace("\r", "\n").split("\n")
            
            for line in lines:
                if 'RBC Histogram.Binary' in line:
                    values = parse_histogram_binary(line)
                    if values:
                        graphs_data['rbc'] = generate_histogram_base64(values, "RBC")
                
                elif 'PLT Histogram.Binary' in line:
                    values = parse_histogram_binary(line)
                    if values:
                        graphs_data['plt'] = generate_histogram_base64(values, "PLT")
                
                elif 'DIFFScatter.Binary' in line or 'DIFF Scatter.Binary' in line:
                    graphs_data['diff'] = 'available'
                
                elif 'BASOScatter.Binary' in line or 'BASO Scatter.Binary' in line:
                    graphs_data['baso'] = 'available'
                    
    except Exception as e:
        print(f"Error extrayendo datos HL7: {e}")

    # =========================
    # LOGO (ruta real en tu proyecto)
    # =========================
    logo_fs_path = os.path.join(
        settings.BASE_DIR,
        "laboratorio", "static", "laboratorio", "img", "logo_confianza.png"
    )
    logo_url = f"file://{logo_fs_path}"

    # =========================
    # CONTEXTO PARA TU TEMPLATE (EL TUYO)
    # =========================
    context = {
        'orden': orden,
        'paciente': orden.paciente,
        'edad': calculate_age(orden.paciente.fecha_nacimiento)
                if orden.paciente.fecha_nacimiento else '',
        'grouped_data': grouped_data,
        'validador': validador_data,
        'logo_path': logo_url,
        'graphs_data': graphs_data,
    }

    # =========================
    # RENDER HTML + PDF
    # =========================
    html_string = render_to_string(
        'laboratorio/informe_resultados_pdf.html',
        context
    )

    html = HTML(string=html_string, base_url=settings.BASE_DIR)
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"informe_resultados_orden_{orden_id}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def pacientes_dashboard(request):
    """
    Dashboard de pacientes con estadísticas y lista de pacientes.
    Calcula:
    - total_pacientes: total de pacientes registrados
    - nuevos_mes: pacientes registrados en el mes actual
    - total_ordenes: total de órdenes registradas
    - ordenes_pendientes: órdenes con estado 'Pendiente'
    - ordenes_en_proceso: órdenes con estado 'En proceso'
    - ordenes_validadas: órdenes con estado 'Validado'
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count

    # Total de pacientes
    total_pacientes = Paciente.objects.count()

    # Pacientes nuevos este mes
    nuevos_mes = Paciente.objects.filter(fecha_registro__month=datetime.now().month).count()

    # Total de órdenes
    total_ordenes = Orden.objects.count()

    # Órdenes pendientes (estado 'Pendiente')
    ordenes_pendientes = Orden.objects.filter(estado='Pendiente').count()

    # Órdenes en proceso (estado 'En proceso')
    ordenes_en_proceso = Orden.objects.filter(estado='En proceso').count()

    # Órdenes validadas (estado 'Validado')
    ordenes_validadas = Orden.objects.filter(estado='Validado').count()

    # Lista de pacientes con count de órdenes (annotate)
    pacientes = Paciente.objects.annotate(
        ordenes_count=Count('orden')
    ).order_by('-creado_en')[:50]

    return render(request, 'laboratorio/pacientes_dashboard.html', {
        'total_pacientes': total_pacientes,
        'nuevos_mes': nuevos_mes,
        'total_ordenes': total_ordenes,
        'ordenes_pendientes': ordenes_pendientes,
        'ordenes_en_proceso': ordenes_en_proceso,
        'ordenes_validadas': ordenes_validadas,
        'pacientes': pacientes,
    })


@login_required
def paciente_historial(request, paciente_id):
    """
    Muestra el historial de órdenes y resultados de un paciente específico.
    """
    paciente = get_object_or_404(Paciente, id=paciente_id)
    ordenes = Orden.objects.filter(paciente=paciente).select_related('paciente').prefetch_related('examenes__examen', 'examenes__resultados').order_by('-fecha')
    return render(request, 'laboratorio/paciente_historial.html', {
        'paciente': paciente,
        'ordenes': ordenes
    })


def simulador_virtual(request):
    """
    Simulador virtual - cliente TCP puro que envía mensajes HL7 al Listener.
    NO escribe en la base de datos - solo consulta y envía al equipo.
    Trama HL7 con campos de longitud fija (como equipo real).
    
    FLUJO: Ingresar Orden -> Consultar DB Local -> Rellenar Interfaz -> Enviar HL7 con Padding al Listener.
    """
    import socket
    from datetime import datetime
    
    error = None
    success = False
    respuesta_raw = None
    numero_orden = None
    nombre_paciente = None
    documento = None
    fecha_nacimiento = None
    edad = None
    sexo = None
    medico = None
    departamento = None
    tipo_paciente = None
    
    # === DETECCIÓN AUTOMÁTICA DEL PUERTO DEL LISTENER ===
    try:
        from configuracion.listener_thread import PORT as LISTENER_PORT
    except ImportError:
        LISTENER_PORT = 2575  # Puerto por defecto (2575)
    
    LISTENER_HOST = '127.0.0.1'
    START_BLOCK = "\x0b"
    END_BLOCK = "\x1c"
    END_LINE = "\r"
    
    # === LONGITUDES DE CAMPO HL7 (CAMPOS FIJOS) ===
    LEN_DOCUMENTO = 20   # PID-3: Identificación del paciente (20 caracteres)
    LEN_NOMBRE = 40      # PID-5: Apellidos y Nombre (40 caracteres)
    LEN_FECHA_NAC = 8    # PID-7: Fecha nacimiento (YYYYMMDD) (8 caracteres)
    LEN_SEXO = 1         # PID-8: Sexo (M/F/U)
    LEN_ORDEN = 15       # ORC-2 y OBR-3: Número de orden (15 caracteres)
    LEN_MEDICO = 20      # Médico tratante (20 caracteres)
    LEN_DEPARTAMENTO = 20  # Departamento (20 caracteres)
    
    if request.method == 'POST':
        numero_orden = request.POST.get('numero_orden', '').strip()
        
        # Los datos del paciente (incluyendo medico, departamento, tipo_paciente) se obtienen de la DB
        # No se aceptan datos del formulario para estos campos
        
        if not numero_orden:
            error = "Por favor ingrese un número de orden."
            messages.error(request, error)
        else:
            # Consultar la orden en la base de datos
            try:
                orden = Orden.objects.get(numero_orden=numero_orden)
                paciente = orden.paciente
            except Orden.DoesNotExist:
                error = f"No se encontró la orden {numero_orden}"
                messages.error(request, error)
                # Mantener los campos visibles con valor "—" aunque no se encontró la orden
                nombre_paciente = "—"
                documento = "—"
                fecha_nacimiento = "—"
                edad = "—"
                sexo = "—"
                medico = "—"
                departamento = "—"
                tipo_paciente = "Rutina"
            else:
                # === EXTRAER DATOS DEL PACIENTE DESDE LA BASE DE DATOS ===
                # Estos datos vienen de la DB, no del formulario
                nombre_paciente = paciente.nombre_completo or ''
                documento = paciente.documento_identidad or ''
                fecha_nacimiento = paciente.fecha_nacimiento.strftime('%Y-%m-%d') if paciente.fecha_nacimiento else None
                sexo = paciente.sexo or 'U'
                
                # Calcular edad
                if paciente.fecha_nacimiento:
                    edad = calculate_age(paciente.fecha_nacimiento)
                else:
                    edad = None
                
                # === EXTRAER MÉDICO Y DEPARTAMENTO DESDE LA BASE DE DATOS ===
                # Médico tratante desde orden.medico (o '—' si no existe)
                medico = orden.medico if orden.medico else '—'
                
                # Departamento: no existe en modelo Orden, usar '—'
                departamento = '—'
                
                # Tipo de paciente: si no existe en la base de datos, usar 'Rutina'
                tipo_paciente = getattr(orden, 'tipo_paciente', None) or 'Rutina'
                
                # Verificar que tenga exámenes asociados
                if not orden.examenes.exists():
                    error = f"La orden {numero_orden} no tiene exámenes asociados."
                    messages.error(request, error)
                else:
                    # === CONSTRUIR MENSAJE HL7 CON CAMPOS DE LONGITUD FIJA ===
                    now = datetime.now().strftime('%Y%m%d%H%M%S')
                    
                    # === DATOS DEL PACIENTE DESDE LA DB (ya extraídos arriba) ===
                    # Aplicar padding (espacios a la derecha) a cada campo HL7
                    
                    # PID-3: Documento de identidad (20 caracteres) - .ljust(20)
                    pid3 = (documento or '').ljust(LEN_DOCUMENTO)[:LEN_DOCUMENTO]
                    
                    # PID-5: Nombre completo (40 caracteres) - .ljust(40)
                    pid5 = (nombre_paciente or '').ljust(LEN_NOMBRE)[:LEN_NOMBRE]
                    
                    # PID-7: Fecha de nacimiento (8 caracteres YYYYMMDD)
                    fecha_nac = ''
                    if fecha_nacimiento:
                        # El input viene como YYYY-MM-DD, convertir a YYYYMMDD
                        try:
                            fecha_nac = fecha_nacimiento.replace('-', '')
                        except Exception:
                            fecha_nac = ''
                    pid7 = fecha_nac.ljust(LEN_FECHA_NAC)[:LEN_FECHA_NAC]
                    
                    # PID-8: Sexo (1 carácter)
                    pid8 = (sexo or 'U')[:1].ljust(LEN_SEXO)
                    
                    # ORC-2 y OBR-3: Número de orden con padding (15 caracteres)
                    orc2 = numero_orden.ljust(LEN_ORDEN)[:LEN_ORDEN]
                    obr3 = numero_orden.ljust(LEN_ORDEN)[:LEN_ORDEN]
                    
                    # Médico tratante (20 caracteres)
                    medico_valor = medico.ljust(LEN_MEDICO)[:LEN_MEDICO]
                    
                    # Departamento (20 caracteres)
                    depto_valor = departamento.ljust(LEN_DEPARTAMENTO)[:LEN_DEPARTAMENTO]
                    
                    # Tipo de paciente con padding de 15 caracteres
                    tipo_pac_valor = (tipo_paciente or 'Rutina').ljust(15)
                    
                    # MSH - Message Header
                    msh = f"MSH|^~\\&|LABORATORIO|SISTEMA|LIS|LIS|{now}||ORM^O01|MSG001|P|2.5.1"
                    
                    # PID - Patient Identification (con campos de longitud fija)
                    pid = f"PID|1|{pid3}||{pid5}|{pid7}|{pid8}"
                    
                    # ORC - Common Order (número de orden en ORC-2 con padding)
                    orc = f"ORC|NW|{orc2}||{orc2}|{medico_valor}"
                    
                    # OBR - Observation Request (número de orden en OBR-3 con padding + departamento + tipo_paciente)
                    obr = f"OBR|1||{obr3}|{now}|CONSULTA|{depto_valor}|{tipo_pac_valor}"
                    
                    # Construir mensaje HL7 completo
                    hl7_message = f"{msh}\r{pid}\r{orc}\r{obr}\r"
                    
                    # === ENVIAR AL LISTENER POR SOCKET TCP ===
                    try:
                        # Envolver el mensaje con caracteres de control HL7
                        mensaje_completo = START_BLOCK + hl7_message + END_BLOCK + END_LINE
                        
                        # Conectar al listener y enviar
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(10)  # Timeout de 10 segundos
                        sock.connect((LISTENER_HOST, LISTENER_PORT))
                        
                        # Enviar mensaje
                        sock.send(mensaje_completo.encode('utf-8'))
                        
                        # Recibir respuesta del listener
                        respuesta_bytes = sock.recv(8192)
                        sock.close()
                        
                        # Decodificar respuesta
                        if respuesta_bytes:
                            # Quitar caracteres de control HL7
                            respuesta_decoded = respuesta_bytes.decode('utf-8', errors='ignore')
                            # Buscar el contenido entre START_BLOCK y END_BLOCK
                            if START_BLOCK in respuesta_decoded:
                                start = respuesta_decoded.find(START_BLOCK) + 1
                                end = respuesta_decoded.find(END_BLOCK)
                                respuesta_raw = respuesta_decoded[start:end]
                            else:
                                respuesta_raw = respuesta_decoded
                            
                            # Verificar ACK
                            if 'MSA|AA' in respuesta_raw:
                                success = True
                            elif 'MSA|AE' in respuesta_raw or 'MSA|AR' in respuesta_raw:
                                error = f"Error del Listener: {respuesta_raw}"
                                messages.error(request, error)
                            else:
                                # Respuesta de consulta (ADR^A19 con datos del paciente)
                                success = True
                        else:
                            error = "No se recibió respuesta del Listener."
                            messages.error(request, error)
                        
                    except socket.timeout:
                        error = f"Timeout conectando al Listener en {LISTENER_HOST}:{LISTENER_PORT}. ¿Está el listener iniciado?"
                        messages.error(request, error)
                    except ConnectionRefusedError:
                        error = f"Conexión rechazada por el Listener en {LISTENER_HOST}:{LISTENER_PORT}. Verifica que el listener esté corriendo."
                        messages.error(request, error)
                    except Exception as e:
                        error = f"Error al enviar al Listener: {str(e)}"
                        messages.error(request, error)

    return render(request, 'laboratorio/simulador_virtual.html', {
        'error': error,
        'success': success,
        'respuesta_raw': respuesta_raw,
        'numero_orden': numero_orden,
        'nombre_paciente': nombre_paciente,
        'documento': documento,
        'fecha_nacimiento': fecha_nacimiento,
        'edad': edad,
        'sexo': sexo,
        'medico': medico,
        'departamento': departamento,
        'tipo_paciente': tipo_paciente,
    })


def generar_valor_parametro(param):
    """Genera un valor aleatorio dentro del rango de referencia del parámetro."""
    import random
    referencia = param.referencia
    
    if not referencia:
        return ''
    
    try:
        # Parsear rango de referencia (ej: "12.0-17.5" o "4.5-11.0")
        referencia = referencia.replace(',', '.')
        if '-' in referencia:
            partes = referencia.split('-')
            min_val = float(partes[0].strip())
            max_val = float(partes[1].strip())
            
            # Generar valor dentro del rango (con margen del 80% al 120% del rango)
            margen = (max_val - min_val) * 0.2
            valor = random.uniform(min_val + margen * 0.1, max_val - margen * 0.1)
            
            # Redondear a 2 decimales
            return f"{valor:.2f}"
    except (ValueError, AttributeError):
        pass
    
    return ''


def generar_resultados_default(examen):
    """Genera resultados por defecto según el tipo de examen."""
    import random
    
    nombre = examen.nombre.lower()
    resultados = []
    
    # Hematología
    if 'hemoglobina' in nombre or 'hb' in nombre:
        resultados = [
            {'parametro': 'Hemoglobina', 'valor': f"{random.uniform(12.0, 17.0):.2f}", 'unidad': 'g/dL', 'referencia': '12.0-17.5'},
            {'parametro': 'Hematocrito', 'valor': f"{random.uniform(36, 50):.2f}", 'unidad': '%', 'referencia': '36-50'},
            {'parametro': 'Eritrocitos', 'valor': f"{random.uniform(4.0, 6.0):.2f}", 'unidad': 'x10^6/µL', 'referencia': '4.0-6.0'},
        ]
    elif 'glóbulos' in nombre or 'leucocitos' in nombre or 'gb' in nombre:
        resultados = [
            {'parametro': 'Leucocitos', 'valor': f"{random.uniform(4.5, 11.0):.2f}", 'unidad': 'x10^3/µL', 'referencia': '4.5-11.0'},
            {'parametro': 'Neutrófilos', 'valor': f"{random.uniform(40, 70):.2f}", 'unidad': '%', 'referencia': '40-70'},
            {'parametro': 'Linfocitos', 'valor': f"{random.uniform(20, 45):.2f}", 'unidad': '%', 'referencia': '20-45'},
            {'parametro': 'Monocitos', 'valor': f"{random.uniform(2, 10):.2f}", 'unidad': '%', 'referencia': '2-10'},
            {'parametro': 'Eosinófilos', 'valor': f"{random.uniform(1, 5):.2f}", 'unidad': '%', 'referencia': '1-5'},
            {'parametro': 'Basófilos', 'valor': f"{random.uniform(0, 1):.2f}", 'unidad': '%', 'referencia': '0-1'},
        ]
    elif 'plaquetas' in nombre or 'trombocitos' in nombre:
        resultados = [
            {'parametro': 'Plaquetas', 'valor': f"{random.uniform(150, 400):.2f}", 'unidad': 'x10^3/µL', 'referencia': '150-400'},
        ]
    # Química sanguínea
    elif 'glucosa' in nombre or 'glucemia' in nombre:
        resultados = [
            {'parametro': 'Glucosa', 'valor': f"{random.uniform(70, 100):.2f}", 'unidad': 'mg/dL', 'referencia': '70-100'},
        ]
    elif 'creatinina' in nombre:
        resultados = [
            {'parametro': 'Creatinina', 'valor': f"{random.uniform(0.7, 1.3):.2f}", 'unidad': 'mg/dL', 'referencia': '0.7-1.3'},
        ]
    elif 'urea' in nombre:
        resultados = [
            {'parametro': 'Urea', 'valor': f"{random.uniform(15, 45):.2f}", 'unidad': 'mg/dL', 'referencia': '15-45'},
        ]
    elif 'ácido úrico' in nombre or 'urico' in nombre:
        resultados = [
            {'parametro': 'Ácido Úrico', 'valor': f"{random.uniform(3.5, 7.2):.2f}", 'unidad': 'mg/dL', 'referencia': '3.5-7.2'},
        ]
    elif 'colesterol' in nombre:
        resultados = [
            {'parametro': 'Colesterol Total', 'valor': f"{random.uniform(150, 200):.2f}", 'unidad': 'mg/dL', 'referencia': '0-200'},
            {'parametro': 'HDL', 'valor': f"{random.uniform(40, 60):.2f}", 'unidad': 'mg/dL', 'referencia': '40-60'},
            {'parametro': 'LDL', 'valor': f"{random.uniform(100, 130):.2f}", 'unidad': 'mg/dL', 'referencia': '0-130'},
            {'parametro': 'Triglicéridos', 'valor': f"{random.uniform(50, 150):.2f}", 'unidad': 'mg/dL', 'referencia': '0-150'},
        ]
    elif 'transaminasa' in nombre or 'alt' in nombre or 'ast' in nombre:
        resultados = [
            {'parametro': 'ALT (TGP)', 'valor': f"{random.uniform(7, 56):.2f}", 'unidad': 'U/L', 'referencia': '7-56'},
            {'parametro': 'AST (TGO)', 'valor': f"{random.uniform(10, 40):.2f}", 'unidad': 'U/L', 'referencia': '10-40'},
        ]
    elif 'fosfatasa' in nombre and 'alcalina' in nombre:
        resultados = [
            {'parametro': 'Fosfatasa Alcalina', 'valor': f"{random.uniform(44, 147):.2f}", 'unidad': 'U/L', 'referencia': '44-147'},
        ]
    elif 'bilirrubina' in nombre:
        resultados = [
            {'parametro': 'Bilirrubina Total', 'valor': f"{random.uniform(0.1, 1.2):.2f}", 'unidad': 'mg/dL', 'referencia': '0.1-1.2'},
            {'parametro': 'Bilirrubina Directa', 'valor': f"{random.uniform(0.0, 0.3):.2f}", 'unidad': 'mg/dL', 'referencia': '0-0.3'},
            {'parametro': 'Bilirrubina Indirecta', 'valor': f"{random.uniform(0.1, 0.9):.2f}", 'unidad': 'mg/dL', 'referencia': '0.1-0.9'},
        ]
    elif 'proteína' in nombre:
        resultados = [
            {'parametro': 'Proteína Total', 'valor': f"{random.uniform(6.0, 8.3):.2f}", 'unidad': 'g/dL', 'referencia': '6.0-8.3'},
            {'parametro': 'Albúmina', 'valor': f"{random.uniform(3.5, 5.5):.2f}", 'unidad': 'g/dL', 'referencia': '3.5-5.5'},
        ]
    elif 'calcio' in nombre:
        resultados = [
            {'parametro': 'Calcio', 'valor': f"{random.uniform(8.5, 10.5):.2f}", 'unidad': 'mg/dL', 'referencia': '8.5-10.5'},
        ]
    elif 'fósforo' in nombre or 'fosforo' in nombre:
        resultados = [
            {'parametro': 'Fósforo', 'valor': f"{random.uniform(2.5, 4.5):.2f}", 'unidad': 'mg/dL', 'referencia': '2.5-4.5'},
        ]
    elif 'magnesio' in nombre:
        resultados = [
            {'parametro': 'Magnesio', 'valor': f"{random.uniform(1.5, 2.5):.2f}", 'unidad': 'mg/dL', 'referencia': '1.5-2.5'},
        ]
    elif 'sodio' in nombre:
        resultados = [
            {'parametro': 'Sodio', 'valor': f"{random.uniform(136, 145):.2f}", 'unidad': 'mEq/L', 'referencia': '136-145'},
        ]
    elif 'potasio' in nombre:
        resultados = [
            {'parametro': 'Potasio', 'valor': f"{random.uniform(3.5, 5.0):.2f}", 'unidad': 'mEq/L', 'referencia': '3.5-5.0'},
        ]
    elif 'cloro' in nombre:
        resultados = [
            {'parametro': 'Cloro', 'valor': f"{random.uniform(98, 106):.2f}", 'unidad': 'mEq/L', 'referencia': '98-106'},
        ]
    # Agregar más exámenes según necesidad...
    
    # Si no hay resultados por defecto, generar uno genérico
    if not resultados:
        resultados = [
            {'parametro': examen.nombre, 'valor': 'Resultado generado', 'unidad': '', 'referencia': ''},
        ]
    
    return resultados


def generar_mensaje_hl7(orden, paciente, resultados):
    """Genera un mensaje HL7 de respuesta simulado."""
    from datetime import datetime
    
    fecha_hl7 = datetime.now().strftime('%Y%m%d%H%M%S')
    fechaNac = paciente.fecha_nacimiento.strftime('%Y%m%d') if paciente.fecha_nacimiento else ''
    
    # Construir mensaje HL7
    hl7_parts = []
    
    # MSH - Message Header
    hl7_parts.append(f"MSH|^~\\&|LABORATORIO|SISTEMA|LIS|LIS|{fecha_hl7}||ORU^R01|MSG001|P|2.5.1")
    
    # PID - Patient Identification
    hl7_parts.append(f"PID|1||{paciente.documento_identidad}||{paciente.nombre_completo}^{paciente.nombre_completo}||{fechaNac}|{paciente.sexo}")
    
    # ORC - Common Order
    hl7_parts.append(f"ORC|RE||{orden.numero_orden}")
    
    # OBR - Observation Request
    hl7_parts.append(f"OBR|1||{orden.numero_orden}|{orden.fecha.strftime('%Y%m%d%H%M%S')}|{orden.tipo}")
    
    # OBX - Observation Result
    for i, res in enumerate(resultados, 1):
        valor = res.get('valor', '')
        unidad = res.get('unidad', '')
        referencia = res.get('referencia', '')
        hl7_parts.append(f"OBX|{i}|NM|{res.get('parametro', '')}||{valor}|{unidad}||||||F|||{fecha_hl7}")
    
    return '\n'.join(hl7_parts)


def simulador(request):
    """
    Página simulador - vista principal del simulador.
    """
    return render(request, 'laboratorio/simulador.html')


# ------------------------------
# MÓDULO DE PROFORMAS
# ------------------------------
from datetime import timedelta

@login_required
def proforma_lista(request):
    """
    Lista de proformas activas (no vencidas).
    Las proformas con más de 10 días de antigüedad se ocultan automáticamente.
    """
    from django.utils import timezone
    
    hoy = timezone.now().date()
    fecha_limite = hoy - timedelta(days=10)
    
    # Mostrar solo proformas creadas en los últimos 10 días
    proformas = Proforma.objects.filter(
        fecha_creacion__date__gte=fecha_limite
    ).select_related('paciente').prefetch_related('examenes__examen').order_by('-fecha_creacion')
    
    return render(request, 'laboratorio/proforma_lista.html', {
        'proformas': proformas,
    })


@login_required
def proforma_nueva(request):
    """
    Formulario para crear una nueva proforma.
    """
    if request.method == 'POST':
        documento = request.POST.get('documento_identidad', '').strip()
        nombre = request.POST.get('nombre_completo', '').strip()
        medico = request.POST.get('medico', '').strip()
        mostrar_precios = request.POST.get('mostrar_precios') == 'on'
        examenes_codigos = request.POST.getlist('examen_codigo[]')
        examenes_precios = request.POST.getlist('examen_precio[]')
        
        if not documento or not nombre:
            messages.error(request, "El documento y nombre del paciente son obligatorios.")
            return redirect('proforma_nueva')
        
        if not examenes_codigos:
            messages.error(request, "Debe seleccionar al menos un examen.")
            return redirect('proforma_nueva')
        
        # Obtener o crear paciente
        paciente, _ = Paciente.objects.get_or_create(
            documento_identidad=documento,
            defaults={'nombre_completo': nombre}
        )
        
        # Calcular total
        total = 0
        for idx, codigo in enumerate(examenes_codigos):
            try:
                precio = float(examenes_precios[idx]) if idx < len(examenes_precios) else 0
                total += precio
            except (ValueError, TypeError):
                pass
        
        # Crear proforma
        proforma = Proforma.objects.create(
            paciente=paciente,
            medico=medico,
            mostrar_precios=mostrar_precios,
            total=total,
            creado_por=request.user
        )
        
        # Crear exámenes asociados
        for idx, codigo in enumerate(examenes_codigos):
            try:
                examen = Examen.objects.get(codigo=codigo)
                precio = float(examenes_precios[idx]) if idx < len(examenes_precios) else float(examen.precio)
                ProformaExamen.objects.create(
                    proforma=proforma,
                    examen=examen,
                    precio_unitario=precio
                )
            except Examen.DoesNotExist:
                continue
        
        messages.success(request, f"Proforma {proforma.numero_proforma} creada correctamente. Puede ver el PDF haciendo clic en el botón PDF.")
        return redirect('proforma_lista')
    
    return render(request, 'laboratorio/proforma_form.html')


@login_required
def proforma_pdf(request, proforma_id):
    """
    Genera el PDF de la proforma usando ReportLab.
    """
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    
    proforma = get_object_or_404(Proforma, id=proforma_id)
    examenes = proforma.examenes.select_related('examen').all()
    
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Encabezado
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, "PROFORMA")
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Número: {proforma.numero_proforma}")
    c.drawString(50, height - 85, f"Fecha: {proforma.fecha_creacion.strftime('%d/%m/%Y')}")
    c.drawString(50, height - 100, f"Válido hasta: {proforma.fecha_vencimiento.strftime('%d/%m/%Y')}")
    
    # Datos del paciente
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 130, "DATOS DEL PACIENTE")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 150, f"Paciente: {proforma.paciente.nombre_completo}")
    c.drawString(50, height - 165, f"Documento: {proforma.paciente.documento_identidad}")
    if proforma.medico:
        c.drawString(50, height - 180, f"Médico: {proforma.medico}")
    
    # Tabla de exámenes
    y = height - 220
    
    # Encabezado de tabla
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Código")
    if proforma.mostrar_precios:
        c.drawString(120, y, "Examen")
        c.drawString(350, y, "Precio")
    else:
        c.drawString(120, y, "Examen")
    
    y -= 15
    c.setLineWidth(0.5)
    c.line(50, y + 10, 500, y + 10)
    
    c.setFont("Helvetica", 9)
    
    for item in examenes:
        if y < 50:
            c.showPage()
            y = height - 50
        
        c.drawString(50, y, item.examen.codigo)
        if proforma.mostrar_precios:
            c.drawString(120, y, item.examen.nombre[:35] if len(item.examen.nombre) > 35 else item.examen.nombre)
            c.drawString(350, y, f"${item.precio_unitario:.2f}")
        else:
            c.drawString(120, y, item.examen.nombre[:45] if len(item.examen.nombre) > 45 else item.examen.nombre)
        y -= 18
    
    # Total
    y -= 10
    c.line(50, y + 10, 500, y + 10)
    y -= 5
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"TOTAL: ${proforma.total:.2f}")
    
    # Observaciones
    if proforma.observaciones:
        y -= 40
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Observaciones:")
        y -= 15
        c.setFont("Helvetica", 9)
        c.drawString(50, y, proforma.observaciones[:100] if len(proforma.observaciones) > 100 else proforma.observaciones)
    
    c.save()
    buffer.seek(0)
    
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="proforma_{proforma.numero_proforma}.pdf"'
    return response


@login_required
def proforma_pdf_popup(request, proforma_id):
    """
    Vista que abre el PDF en una nueva ventana y luego redirige a la lista.
    """
    proforma = get_object_or_404(Proforma, id=proforma_id)
    
    # Renderizar template que abre el PDF en nueva ventana
    return render(request, 'laboratorio/proforma_pdf_popup.html', {
        'proforma': proforma,
        'pdf_url': reverse('proforma_pdf', args=[proforma_id])
    })


@login_required
def proforma_eliminar(request, proforma_id):
    """
    Elimina una proforma.
    """
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma.delete()
    messages.success(request, "Proforma eliminada correctamente.")
    return redirect('proforma_lista')


@login_required
def proforma_generar_orden(request, proforma_id):
    """
    Genera una orden a partir de una proforma.
    """
    proforma = get_object_or_404(Proforma.objects.prefetch_related('examenes__examen'), id=proforma_id)
    
    # Generar número de orden correlativo
    max_num = 999
    for s in Orden.objects.values_list('numero_orden', flat=True):
        ds = ''.join(ch for ch in (s or '') if ch.isdigit())
        if ds:
            try:
                n = int(ds)
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
    siguiente = max_num + 1
    numero = f"{siguiente:06d}"
    
    # Crear la orden
    orden = Orden.objects.create(
        paciente=proforma.paciente,
        numero_orden=numero,
        medico=proforma.medico,
        observaciones=proforma.observaciones,
        creado_por=request.user
    )
    
    # Crear los exámenes de la orden
    # IMPORTANTE: guardar los datos ANTES de eliminar la proforma
    examenes_proforma = proforma.examenes.select_related('examen').all()
    examenes_data = []
    for pe in examenes_proforma:
        examenes_data.append({
            'examen_id': pe.examen.id,
            'precio_unitario': pe.precio_unitario
        })
    
    for pe in examenes_data:
        OrdenExamen.objects.create(
            orden=orden,
            examen_id=pe['examen_id'],
            precio=pe['precio_unitario'],
            creado_por=request.user
        )
    
    # Calcular total de la orden
    orden.total = sum(oe.precio for oe in orden.examenes.all())
    orden.save()
    
    # Eliminar la proforma ya que se convirtió en orden
    proforma.delete()
    
    messages.success(request, f"Orden {numero} creada correctamente desde proforma.")
    return redirect('detalle_orden', orden_id=orden.id)
