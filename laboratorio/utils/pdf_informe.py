"""
Helper para generación automática de informes PDF.
Utiliza la clase InformeCanvas de views_informe.py para generar PDFs profesionales.
"""

import os
import io
from django.conf import settings
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# Importar la clase existente desde views_informe
from laboratorio.views_informe import InformeCanvas


def generar_pdf_para_orden(orden, guardar=True, retorno_bytes=False):
    """
    Genera un informe PDF para una orden específica.
    
    Args:
        orden: Instancia del modelo Orden
        guardar: Si True, guarda el PDF en MEDIA_ROOT/informes/
        retorno_bytes: Si True, retorna los bytes del PDF en lugar de guardarlo
    
    Returns:
        Si retorno_bytes=True: bytes del PDF
        Si guardar=True: ruta del archivo guardado
        None si hay error
    """
    try:
        # Crear buffer para el PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        
        # Usar la clase InformeCanvas existente
        report_generator = InformeCanvas(c, orden)
        report_generator.generate_report()
        
        # Obtener los bytes del PDF
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        if retorno_bytes:
            return pdf_bytes
        
        if guardar:
            # Guardar en MEDIA_ROOT/informes/
            informes_dir = os.path.join(settings.MEDIA_ROOT, 'informes')
            os.makedirs(informes_dir, exist_ok=True)
            
            # Nombre del archivo: numero_orden.pdf
            numero_orden = orden.numero_orden or f"orden_{orden.id}"
            filename = f"{numero_orden}.pdf"
            filepath = os.path.join(informes_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(pdf_bytes)
            
            # Actualizar campo pdf_ruta en la orden si existe
            try:
                orden.pdf_ruta = f"informes/{filename}"
                orden.save(update_fields=['pdf_ruta'])
            except Exception:
                pass  # El campo puede no existir aún
            
            return filepath
        
        return None
        
    except Exception as e:
        print(f"ERROR generando PDF para orden {orden.numero_orden}: {e}")
        import traceback
        traceback.print_exc()
        return None


def generar_pdf_response(orden):
    """
    Genera una respuesta HTTP con el PDF para descarga/invisualización directa.
    
    Args:
        orden: Instancia del modelo Orden
    
    Returns:
        HttpResponse con el PDF
    """
    pdf_bytes = generar_pdf_para_orden(orden, guardar=False, retorno_bytes=True)
    
    if not pdf_bytes:
        return HttpResponse("Error generando PDF", status=500)
    
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    numero_orden = orden.numero_orden or f"orden_{orden.id}"
    response['Content-Disposition'] = f'inline; filename="informe_{numero_orden}.pdf"'
    
    return response
