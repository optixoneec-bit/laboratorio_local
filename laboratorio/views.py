# laboratorio/views.py
import os
from datetime import date # Necesario para la función calculate_age
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
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


from .models import Paciente, Orden, OrdenExamen, Resultado, Examen, ExamenParametro


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
    query = request.GET.get('q', '')
    ordenes = Orden.objects.all().order_by('-fecha')
    if query:
        ordenes = ordenes.filter(paciente__nombre_completo__icontains=query) | ordenes.filter(numero_orden__icontains=query)
    return render(request, 'laboratorio/lista_ordenes.html', {'ordenes': ordenes, 'query': query})


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
    pacientes = Paciente.objects.all().order_by("-creado_en")
    return render(request, "laboratorio/pacientes_lista.html", {"pacientes": pacientes})

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
