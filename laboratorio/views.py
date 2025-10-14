from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.template.loader import render_to_string
from django.contrib.auth.views import redirect_to_login
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd
from django.core.files.storage import default_storage
from django.core.paginator import Paginator

from .models import Paciente, Orden, OrdenExamen, Resultado, Examen


# ------------------------------
# Gestión de resultados y validación
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
# Vistas principales del sistema
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
    examenes = orden.examenes.all()
    return render(request, 'laboratorio/resultados.html', {'orden': orden, 'examenes': examenes})


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
# Pacientes (AJAX)
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
# CATÁLOGO DE EXÁMENES
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


# ------------------------------
# BUSCADOR GLOBAL DE EXÁMENES (AJAX)
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
