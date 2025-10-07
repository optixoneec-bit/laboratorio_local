from django.urls import path
from django.http import HttpResponse

def inicio(request):
    return HttpResponse("<h1>Mini Sistema de Laboratorio</h1><p>Ya estamos en marcha 🚀</p>")

urlpatterns = [
    path('', inicio, name='inicio'),
]
