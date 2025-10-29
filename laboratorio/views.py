# laboratorio/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string
from django.contrib.auth.views import redirect_to_login
from django.template import TemplateDoesNotExist
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
import json
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.core.files.storage import default_storage
import csv
import io
from django.http import HttpResponse
try:
    import pandas as pd
except Exception:
    pd = None


from .models import Paciente, Orden, OrdenExamen, Resultado, Examen, ExamenParametro



# ------------------------------
# Gestión de resultados y validación (TU CÓDIGO ORIGINAL)
# ------------------------------

@login_required
def registrar_resultado(request, orden_examen_id):
    orden_examen = get_object_or_404(OrdenExamen, id=orden_examen_id)
    if request.method == 'POST':
        parametro = request.POST.get('parametro')
        valor = request.POST.get('valor')
        unidad = request.POST.get('unidad')
        referencia = request.POST.get('referencia')
        if parametro and valor:
            Resultado.objects.create(
                orden_examen=orden_examen,
                parametro=parametro,
                valor=valor,
                unidad=unidad,
                referencia=referencia,
            )
            orden_examen.estado = "Procesado"
            orden_examen.save()
            orden = orden_examen.orden
            orden.estado = "En proceso"
            orden.save()
            return JsonResponse({'status': 'ok', 'message': 'Resultado registrado correctamente'})
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
        numero = f"ORD{Orden.objects.count()+1:05d}"
        orden = Orden.objects.create(
            paciente=paciente,
            numero_orden=numero,
            creado_por=request.user
        )

        # -------------------------------------------
        # NUEVO BLOQUE: guardar exámenes seleccionados
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

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('laboratorio/partials/orden_item.html', {'orden': orden})
            return JsonResponse({'status': 'ok', 'html': html})
        else:
            messages.success(request, f"Orden {numero} creada correctamente")
            return redirect('detalle_orden', orden_id=orden.id)
    return render(request, 'laboratorio/orden_form.html')


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
@require_http_methods(["POST"])
def modal_resumen_resultados(request):
    oe_id = request.POST.get('orden_examen_id')
    if not oe_id:
        return JsonResponse({'status': 'error', 'message': 'Falta orden_examen_id'}, status=400)

    parametros = request.POST.getlist('parametro[]') or request.POST.getlist('parametro')
    valores    = request.POST.getlist('valor[]')     or request.POST.getlist('valor')
    unidades   = request.POST.getlist('unidad[]')    or request.POST.getlist('unidad')
    refs       = request.POST.getlist('referencia[]')or request.POST.getlist('referencia')
    ids_exist  = request.POST.getlist('resultado_id[]') or request.POST.getlist('resultado_id')

    if not (parametros and valores):
        return JsonResponse({'status': 'error', 'message': 'No hay datos de resultados para resumir'}, status=400)

    n = max(len(parametros), len(valores), len(unidades or []), len(refs or []), len(ids_exist or []))
    def at(lst, i): return lst[i] if (lst and i < len(lst)) else ''

    items = []
    for i in range(n):
        p = (at(parametros, i) or '').strip()
        v = (at(valores, i) or '').strip()
        u = (at(unidades, i) or '').strip()
        r = (at(refs, i) or '').strip()
        rid = (at(ids_exist, i) or '').strip()
        if p or v or u or r or rid:
            items.append({'resultado_id': rid, 'parametro': p, 'valor': v, 'unidad': u, 'referencia': r})

    orden_examen = get_object_or_404(
        OrdenExamen.objects.select_related('orden', 'examen'),
        id=oe_id
    )
    ctx = {
        'orden_examen': orden_examen,
        'examen': orden_examen.examen,
        'paciente': getattr(orden_examen.orden, 'paciente', None),
        'items': items,
    }
    html = render_to_string('laboratorio/partials/resumen_resultados.html', context=ctx, request=request)
    return JsonResponse({'status': 'ok', 'html': html})


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def guardar_resultados_ajax(request):
    oe_id = request.POST.get('orden_examen_id')
    if not oe_id:
        return JsonResponse({'status': 'error', 'message': 'Falta orden_examen_id'}, status=400)

    orden_examen = get_object_or_404(OrdenExamen, id=oe_id)

    parametros = request.POST.getlist('parametro[]') or request.POST.getlist('parametro')
    valores    = request.POST.getlist('valor[]')     or request.POST.getlist('valor')
    unidades   = request.POST.getlist('unidad[]')    or request.POST.getlist('unidad')
    refs       = request.POST.getlist('referencia[]')or request.POST.getlist('referencia')
    ids_exist  = request.POST.getlist('resultado_id[]') or request.POST.getlist('resultado_id')

    if not (parametros and valores):
        return JsonResponse({'status': 'error', 'message': 'No hay datos de resultados para guardar'}, status=400)

    n = max(len(parametros), len(valores), len(unidades or []), len(refs or []), len(ids_exist or []))
    def at(lst, i): return lst[i] if (lst and i < len(lst)) else ''

    creados, actualizados = 0, 0
    for i in range(n):
        p = (at(parametros, i) or '').strip()
        v = (at(valores, i) or '').strip()
        u = (at(unidades, i) or '').strip()
        r = (at(refs, i) or '').strip()
        rid = (at(ids_exist, i) or '').strip()

        if not (p or v or u or r or rid):
            continue

        if rid:
            try:
                res = Resultado.objects.select_for_update().get(id=rid, orden_examen=orden_examen)
                res.parametro = p
                res.valor = v
                res.unidad = u
                res.referencia = r
                res.save(update_fields=['parametro', 'valor', 'unidad', 'referencia'])
                actualizados += 1
            except Resultado.DoesNotExist:
                Resultado.objects.create(
                    orden_examen=orden_examen,
                    parametro=p, valor=v, unidad=u, referencia=r
                )
                creados += 1
        else:
            Resultado.objects.create(
                orden_examen=orden_examen,
                parametro=p, valor=v, unidad=u, referencia=r
            )
            creados += 1

    try:
        resultados = Resultado.objects.filter(orden_examen=orden_examen).order_by('id')
        ctx = {
            'orden_examen': orden_examen,
            'examen': getattr(orden_examen, 'examen', None),
            'paciente': getattr(orden_examen.orden, 'paciente', None) if hasattr(orden_examen, 'orden') else None,
            'resultados': resultados,
        }
        html = render_to_string('laboratorio/partials/tabla_resultados.html', context=ctx, request=request)
        return JsonResponse({'status': 'ok', 'message': f'Guardado correcto. Creados: {creados}, actualizados: {actualizados}', 'html': html})
    except Exception:
        return JsonResponse({'status': 'ok', 'message': f'Guardado correcto. Creados: {creados}, actualizados: {actualizados}'})


# Alias para mantener tu URL existente en urls.py
@login_required
@require_http_methods(["POST"])
def guardar_resultados_orden(request):
    return guardar_resultados_ajax(request)


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
    if orden_id:
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
@csrf_exempt
def guardar_resultados_ajax(request):
    """
    Guarda o actualiza los resultados desde la pantalla de carga (AJAX Synlab).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        resultado_id = data.get('id')
        valor = data.get('valor')
        unidad = data.get('unidad')
        referencia = data.get('referencia')
        metodo = data.get('metodo')
        observacion = data.get('observacion')

        resultado = Resultado.objects.get(id=resultado_id)
        resultado.valor = valor
        resultado.unidad = unidad
        resultado.referencia = referencia
        resultado.metodo = metodo
        resultado.observacion = observacion
        resultado.marca_fuera_de_rango()
        resultado.save()

        return JsonResponse({'status': 'ok', 'message': 'Resultado guardado correctamente.'})

    except Resultado.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Resultado no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
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
    Exporta a CSV aplicando el filtro de búsqueda actual.
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
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['codigo_examen','examen','parametro','unidad','referencia','metodo','observacion','acreditado'])
    for p in qs:
        writer.writerow([
            p.examen.codigo,
            p.examen.nombre,
            p.nombre or '',
            p.unidad or '',
            p.referencia or '',
            p.metodo or '',
            p.observacion or '',
            '1' if p.acreditado else '0'
        ])
    response = HttpResponse(out.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename=catalogo_tecnico.csv'
    return response
