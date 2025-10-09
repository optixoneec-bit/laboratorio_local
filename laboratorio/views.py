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
from .models import Paciente, Orden, OrdenExamen, Resultado


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
    # 🔹 Permitir carga AJAX sin error de redirección
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    if request.method == 'POST':
        doc = request.POST.get('documento_identidad')
        nombre = request.POST.get('nombre_completo')
        paciente, _ = Paciente.objects.get_or_create(
            documento_identidad=doc,
            defaults={'nombre_completo': nombre}
        )
        numero = f"ORD{Orden.objects.count()+1:05d}"
        orden = Orden.objects.create(
            paciente=paciente,
            numero_orden=numero,
            creado_por=request.user
        )
        # 🔹 Si la petición viene desde AJAX, responder JSON
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            html = render_to_string('laboratorio/partials/orden_item.html', {'orden': orden})
            return JsonResponse({'status': 'ok', 'html': html})
        else:
            messages.success(request, f"Orden {numero} creada correctamente")
            return redirect('detalle_orden', orden_id=orden.id)

    # 🔹 Render normal del formulario
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
