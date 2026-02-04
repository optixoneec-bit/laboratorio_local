from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django import forms
from django.contrib.auth.models import User, Group, Permission
from django.http import JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.views.decorators.http import require_POST
from functools import wraps, lru_cache

from .listener_thread import start_listener, stop_listener, status_listener
from .models import HL7Mensaje, ConfigGeneral, Equipo, EquipoMapeo
from .forms import ConfigGeneralForm, EquipoForm, EquipoMapeoForm


# ------------------------------
# DASHBOARD CONFIGURACIÓN
# ------------------------------

def config_dashboard(request):
    return render(request, 'configuracion/index.html')


def requiere_modulo(codename):
    """
    Decorador para restringir acceso por 'módulo' usando permisos de Django.
    El permiso se crea automáticamente si no existe, asociado a ConfigGeneral.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            perm_full = f"configuracion.{codename}"
            if request.user.has_perm(perm_full):
                return view_func(request, *args, **kwargs)
            messages.error(request, "No tienes permiso para acceder a este módulo.")
            return redirect('configuracion:dashboard')
        return _wrapped
    return decorator


@login_required
@requiere_modulo('mod_configuracion')
def dashboard_config(request):
    cfg = ConfigGeneral.unica()
    return render(request, 'configuracion/index.html', {'cfg': cfg})


# ------------------------------
# PARÁMETROS GENERALES
# ------------------------------

@login_required
@requiere_modulo('mod_configuracion')
def editar_generales(request):
    cfg = ConfigGeneral.unica()
    if request.method == 'POST':
        form = ConfigGeneralForm(request.POST, request.FILES, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuración guardada correctamente.')
            return redirect('configuracion:dashboard')
        messages.error(request, 'Revisa los campos del formulario.')
    else:
        form = ConfigGeneralForm(instance=cfg)
    return render(request, 'configuracion/generales_form.html', {
        'form': form,
        'cfg': cfg
    })


# ------------------------------
# EQUIPOS - INTEGRACIÓN
# ------------------------------

@login_required
@requiere_modulo('mod_configuracion')
def equipos_lista(request):
    equipos = Equipo.objects.all().order_by('nombre')
    return render(request, 'configuracion/equipos_lista.html', {
        'equipos': equipos,
    })


@login_required
@requiere_modulo('mod_configuracion')
def equipo_nuevo(request):
    if request.method == 'POST':
        form = EquipoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipo creado correctamente.')
            return redirect('configuracion:equipos_lista')
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = EquipoForm()
    return render(request, 'configuracion/equipos_form.html', {
        'form': form,
        'modo': 'nuevo',
    })


@login_required
@requiere_modulo('mod_configuracion')
def equipo_editar(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    if request.method == 'POST':
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Equipo actualizado correctamente.')
            return redirect('configuracion:equipos_lista')
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = EquipoForm(instance=equipo)
    return render(request, 'configuracion/equipos_form.html', {
        'form': form,
        'modo': 'editar',
        'equipo': equipo,
    })


@login_required
@requiere_modulo('mod_configuracion')
def equipo_mapeo_lista(request, equipo_id):
    equipo = get_object_or_404(Equipo, pk=equipo_id)
    mapeos = equipo.mapeos.select_related('examen').all().order_by('codigo_equipo')
    return render(request, 'configuracion/equipos_mapeo.html', {
        'equipo': equipo,
        'mapeos': mapeos,
    })


@login_required
@requiere_modulo('mod_configuracion')
def equipo_mapeo_editar(request, equipo_id, mapeo_id=None):
    equipo = get_object_or_404(Equipo, pk=equipo_id)

    if mapeo_id:
        mapeo = get_object_or_404(EquipoMapeo, pk=mapeo_id, equipo=equipo)
    else:
        mapeo = None

    if request.method == 'POST':
        form = EquipoMapeoForm(request.POST, instance=mapeo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.equipo = equipo
            obj.save()
            messages.success(request, 'Mapeo guardado correctamente.')
            return redirect('configuracion:equipo_mapeo_lista', equipo_id=equipo.id)
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = EquipoMapeoForm(instance=mapeo)

    return render(request, 'configuracion/equipos_mapeo_form.html', {
        'equipo': equipo,
        'form': form,
        'mapeo': mapeo,
    })


# ------------------------------
# MONITOR HL7
# ------------------------------

@login_required
@requiere_modulo('mod_configuracion')
def hl7_dashboard(request):
    mensajes = HL7Mensaje.objects.order_by('-id')[:20]
    return render(request, 'configuracion/hl7_dashboard.html', {
        'mensajes': mensajes,
        'listener_status': status_listener()
    })


@login_required
@requiere_modulo('mod_configuracion')
def hl7_start(request):
    ok = start_listener()
    return JsonResponse({'status': ok})


@login_required
@requiere_modulo('mod_configuracion')
def hl7_stop(request):
    ok = stop_listener()
    return JsonResponse({'status': ok})


@login_required
@requiere_modulo('mod_configuracion')
def hl7_historial(request):
    mensajes = HL7Mensaje.objects.order_by('-id')
    return render(request, 'configuracion/hl7_historial.html', {
        'mensajes': mensajes,
    })


@login_required
@requiere_modulo('mod_configuracion')
def hl7_ver(request, pk):
    msg = get_object_or_404(HL7Mensaje, pk=pk)
    return render(request, 'configuracion/hl7_ver.html', {
        'msg': msg
    })


def _hl7_parse_msh(raw_text):
    """
    Devuelve dict mínimo desde MSH:
      {'app': 'Genrui', 'facility': 'KT-6610'}
    """
    out = {'app': '', 'facility': ''}
    try:
        for line in (raw_text or '').splitlines():
            if line.startswith('MSH|'):
                parts = line.split('|')
                # MSH|^~\&|SENDING_APP|SENDING_FACILITY|...
                out['app'] = (parts[2] or '').strip() if len(parts) > 2 else ''
                out['facility'] = (parts[3] or '').strip() if len(parts) > 3 else ''
                break
    except Exception:
        pass
    return out


def _infer_equipo_for_msg(msg):
    """
    Intenta determinar el Equipo (configuracion.Equipo) para un HL7Mensaje.
    Prioridad:
      1) IP del mensaje contra host del equipo
      2) MSH sending app/facility contra nombre/fabricante/modelo/codigo
    """
    try:
        if msg.ip_equipo:
            eq = (
                Equipo.objects
                .filter(activo=True, host=str(msg.ip_equipo).strip())
                .order_by('id')
                .first()
            )
            if eq:
                return eq
    except Exception:
        pass

    msh = _hl7_parse_msh(getattr(msg, 'mensaje_raw', '') or '')
    app = msh.get('app', '') or ''
    fac = msh.get('facility', '') or ''

    try:
        qs = Equipo.objects.filter(activo=True)
        if app:
            qs = qs.filter(models.Q(nombre__icontains=app) | models.Q(fabricante__icontains=app) | models.Q(codigo__icontains=app))
        if fac:
            qs = qs.filter(models.Q(modelo__icontains=fac) | models.Q(codigo__icontains=fac) | models.Q(nombre__icontains=fac))
        eq = qs.order_by('id').first()
        return eq
    except Exception:
        return None


def _extract_obx_items(raw_text):
    """
    Devuelve lista de dicts:
      [{'code': 'WBC', 'value': '6.5', 'unit': '10^9/L', 'ref': '4.0-10.0', 'type': 'NM'}, ...]
    code = OBX-3 antes de '^'
    value = OBX-5
    unit  = OBX-6
    ref   = OBX-7
    """
    items = []
    for line in (raw_text or '').splitlines():
        line = (line or '').strip()
        if not line.startswith('OBX|'):
            continue
        parts = line.split('|')
        if len(parts) < 6:
            continue

        vtype = (parts[2] or '').strip()  # OBX-2
        obx3 = (parts[3] or '').strip()   # OBX-3
        val = (parts[5] or '').strip()    # OBX-5
        unit = (parts[6] or '').strip() if len(parts) > 6 else ''  # OBX-6
        ref = (parts[7] or '').strip() if len(parts) > 7 else ''   # OBX-7

        code = obx3.split('^')[0].strip() if obx3 else ''
        if not code:
            continue

        items.append({
            'code': code,
            'value': val,
            'unit': unit,
            'ref': ref,
            'type': vtype,
        })
    return items


@login_required
@requiere_modulo('mod_configuracion')
@require_POST
def hl7_aplicar_a_orden(request, pk):
    """
    Aplica el HL7Mensaje a la Orden que coincida con msg.sample_id.
    Usa EquipoMapeo (activo) para convertir OBX -> Resultado.
    """
    msg = get_object_or_404(HL7Mensaje, pk=pk)

    sample_id = (msg.sample_id or '').strip()
    if not sample_id:
        return JsonResponse({'ok': False, 'error': 'HL7 sin sample_id. No se puede enlazar a una Orden.'}, status=400)

    # Importar modelos del laboratorio (tu app de resultados)
    try:
        from laboratorio.models import Orden, OrdenExamen, Resultado
    except Exception:
        return JsonResponse({'ok': False, 'error': 'No se pudo importar modelos de laboratorio.'}, status=500)

    orden = Orden.objects.filter(numero_orden=sample_id).first()
    if not orden:
        return JsonResponse({'ok': False, 'error': f'No existe Orden con numero_orden={sample_id}.'}, status=404)

    equipo = _infer_equipo_for_msg(msg)
    if not equipo:
        return JsonResponse({'ok': False, 'error': 'No se pudo determinar el Equipo para este HL7. (Revisa host/IP o MSH)'}, status=400)

    # Mapeos activos del equipo
    mapeos = (
        EquipoMapeo.objects
        .filter(equipo=equipo, activo=True)
        .select_related('examen')
        .all()
    )
    mapa = {}
    for mp in mapeos:
        if not mp.codigo_equipo:
            continue
        if not mp.examen:
            continue
        mapa[mp.codigo_equipo.strip()] = mp

    if not mapa:
        return JsonResponse({'ok': False, 'error': f'El equipo {equipo.codigo} no tiene mapeos activos con examen asignado.'}, status=400)

    obx_items = _extract_obx_items(msg.mensaje_raw or '')
    if not obx_items:
        return JsonResponse({'ok': False, 'error': 'El HL7 no contiene OBX procesables.'}, status=400)

    creados = 0
    actualizados = 0
    ignorados = 0

    for it in obx_items:
        code = it['code']
        mp = mapa.get(code)
        if not mp:
            ignorados += 1
            continue

        # Saltar binarios (histogram/scatter) aunque estén mapeados por error
        if '.Binary' in code or 'Histogram' in code or 'Scatter' in code:
            ignorados += 1
            continue

        # Determinar OrdenExamen del examen mapeado
        oe, _ = OrdenExamen.objects.get_or_create(
            orden=orden,
            examen=mp.examen,
            defaults={'precio': 0.00, 'estado': 'Pendiente'}
        )

        # Crear/actualizar Resultado por parámetro interno
        param = (mp.parametro or '').strip()
        if not param:
            # Si alguien dejó el parámetro vacío, no podemos guardar
            ignorados += 1
            continue

        obj, created = Resultado.objects.update_or_create(
            orden_examen=oe,
            parametro=param,
            defaults={
                'valor': it['value'] if it['value'] != '' else None,
                'unidad': it['unit'] if it['unit'] != '' else None,
                'referencia': it['ref'] if it['ref'] != '' else None,
            }
        )
        try:
            obj.marca_fuera_de_rango()
            obj.save(update_fields=['fuera_de_rango'])
        except Exception:
            pass

        if created:
            creados += 1
        else:
            actualizados += 1

    # Marcar msg como procesado
    try:
        msg.estado = 'procesado'
        msg.save(update_fields=['estado'])
    except Exception:
        pass

    return JsonResponse({
        'ok': True,
        'orden_id': orden.id,
        'orden_numero': orden.numero_orden,
        'equipo': equipo.codigo,
        'creados': creados,
        'actualizados': actualizados,
        'ignorados': ignorados,
        'total_obx': len(obx_items),
    })


# ------------------------------
# FORMULARIOS USUARIOS / ROLES
# ------------------------------

class UsuarioNuevoForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    groups = forms.ModelMultipleChoiceField(
        label="Roles",
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'is_staff',
            'groups',
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_m2m()
        return user


class UsuarioRolesForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        label="Roles",
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = User
        fields = ['is_active', 'is_staff', 'groups']
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class GrupoPermisosForm(forms.ModelForm):
    """
    Solo maneja el nombre del rol.
    Los permisos de acceso a módulos se gestionan manualmente.
    """
    class Meta:
        model = Group
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }


# ------------------------------
# DEFINICIÓN DE MÓDULOS (COINCIDE CON TU SIDEBAR)
# ------------------------------

MODULOS_DEFINIDOS = [
    # BLOQUE NAVEGACIÓN
    ('mod_inicio', 'Inicio', 'Acceso al panel principal de la aplicación.'),
    ('mod_nueva', 'Nueva', 'Crear una nueva orden de laboratorio.'),
    ('mod_catalogo', 'Catálogo', 'Acceso al catálogo general (listado principal).'),
    ('mod_catalogo_tec', 'Catálogo Téc.', 'Acceso al catálogo técnico de exámenes.'),
    ('mod_resultados', 'Resultados', 'Consulta de resultados emitidos.'),
    ('mod_validacion', 'Validación', 'Pantalla de validación de resultados.'),
    ('mod_precios', 'Precios', 'Módulo de configuración y simulación de precios.'),

    # BLOQUE SISTEMA
    ('mod_pacientes', 'Pacientes', 'Módulo de gestión de pacientes.'),
    ('mod_configuracion', 'Configuración', 'Módulo de configuración (parámetros, equipos, HL7, roles y usuarios).'),
]


@lru_cache(maxsize=1)
def _get_permisos_modulos():
    """
    Crea (si no existen) y devuelve un dict {codigo: Permission}
    usando ConfigGeneral como content_type base.
    """
    ct = ContentType.objects.get_for_model(ConfigGeneral)
    permisos = {}
    for codename, nombre_corto, descripcion in MODULOS_DEFINIDOS:
        perm, _ = Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={'name': f'Acceso módulo: {nombre_corto}'}
        )
        permisos[codename] = perm
    return permisos


def _modulos_para_grupo(grupo):
    """
    Devuelve una lista de dicts para usar en el template:
    [
      {'code': 'mod_configuracion', 'name': 'Configuración', 'description': '...', 'checked': True},
      ...
    ]
    """
    permisos_mod = _get_permisos_modulos()
    seleccionados = set()
    if grupo is not None:
        seleccionados = set(grupo.permissions.values_list('id', flat=True))

    modulos = []
    for codename, nombre_corto, descripcion in MODULOS_DEFINIDOS:
        perm = permisos_mod[codename]
        modulos.append({
            'code': codename,
            'name': nombre_corto,
            'description': descripcion,
            'checked': perm.id in seleccionados,
        })
    return modulos


# ------------------------------
# VISTAS ROLES / USUARIOS
# ------------------------------

@login_required
@requiere_modulo('mod_configuracion')
def roles_dashboard(request):
    grupos = Group.objects.all().order_by('name')
    usuarios = User.objects.all().order_by('username')
    return render(request, 'configuracion/roles_dashboard.html', {
        'grupos': grupos,
        'usuarios': usuarios,
    })


@login_required
@requiere_modulo('mod_configuracion')
def grupo_nuevo(request):
    return grupo_editar(request, pk=None)


@login_required
@requiere_modulo('mod_configuracion')
def grupo_editar(request, pk=None):
    if pk:
        grupo = get_object_or_404(Group, pk=pk)
    else:
        grupo = None

    permisos_mod = _get_permisos_modulos()

    if request.method == 'POST':
        form = GrupoPermisosForm(request.POST, instance=grupo)
        if form.is_valid():
            grupo = form.save()

            # actualizar sólo permisos de módulos definidos
            seleccionados_codigos = request.POST.getlist('modulos')

            # Evitar que te bloquees: si estás editando un rol al que perteneces,
            # forzamos que conserve acceso a Configuración (a menos que seas superuser).
            if (not request.user.is_superuser) and (grupo is not None) and request.user.groups.filter(id=grupo.id).exists():
                if 'mod_configuracion' not in seleccionados_codigos:
                    seleccionados_codigos.append('mod_configuracion')
                    messages.warning(request, 'No puedes quitarte el acceso a Configuración desde tu propio rol. Se mantuvo habilitado.')

            # Preservar permisos NO relacionados a módulos y actualizar SOLO los de módulos definidos
            mod_perm_ids = [p.id for p in permisos_mod.values()]
            permisos_a_conservar = list(grupo.permissions.exclude(id__in=mod_perm_ids))

            permisos_seleccionados = []
            for code in seleccionados_codigos:
                perm = permisos_mod.get(code)
                if perm:
                    permisos_seleccionados.append(perm)

            grupo.permissions.set(permisos_a_conservar + permisos_seleccionados)

            # limpiar caché de permisos del usuario en sesión (Django cachea permisos)
            if hasattr(request.user, '_perm_cache'):
                del request.user._perm_cache

            messages.success(request, 'Rol guardado correctamente.')
            return redirect('configuracion:roles_dashboard')
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = GrupoPermisosForm(instance=grupo)

    modulos = _modulos_para_grupo(grupo)

    return render(request, 'configuracion/grupo_form.html', {
        'form': form,
        'grupo': grupo,
        'modulos': modulos,
    })


@login_required
@requiere_modulo('mod_configuracion')
def usuario_nuevo(request):
    if request.method == 'POST':
        form = UsuarioNuevoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('configuracion:roles_dashboard')
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = UsuarioNuevoForm()

    return render(request, 'configuracion/usuario_nuevo_form.html', {
        'form': form,
    })


@login_required
@requiere_modulo('mod_configuracion')
def usuario_editar_roles(request, user_id):
    usuario = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = UsuarioRolesForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()

            # limpiar caché de permisos (Django cachea permisos por-request)
            if hasattr(usuario, '_perm_cache'):
                del usuario._perm_cache
            if hasattr(request.user, '_perm_cache'):
                del request.user._perm_cache

            messages.success(request, 'Roles y permisos actualizados correctamente.')
            return redirect('configuracion:roles_dashboard')
        messages.error(request, 'Revisa los datos del formulario.')
    else:
        form = UsuarioRolesForm(instance=usuario)

    return render(request, 'configuracion/usuario_roles_form.html', {
        'usuario': usuario,
        'form': form,
    })


# ------------------------------
# ELIMINAR ROLES Y USUARIOS
# ------------------------------

@login_required
@requiere_modulo('mod_configuracion')
@require_POST
def grupo_eliminar(request, pk):
    grupo = get_object_or_404(Group, pk=pk)
    nombre = grupo.name
    grupo.delete()
    messages.success(request, f'Rol "{nombre}" eliminado correctamente.')
    return redirect('configuracion:roles_dashboard')


@login_required
@requiere_modulo('mod_configuracion')
@require_POST
def usuario_eliminar(request, user_id):
    usuario = get_object_or_404(User, pk=user_id)
    if usuario == request.user:
        messages.error(request, 'No puedes eliminar tu propio usuario.')
        return redirect('configuracion:roles_dashboard')
    nombre = usuario.username
    usuario.delete()
    messages.success(request, f'Usuario "{nombre}" eliminado correctamente.')
    return redirect('configuracion:roles_dashboard')
