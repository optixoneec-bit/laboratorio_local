# Mini Sistema de Laboratorio Local

## Instrucciones

1. Crea el entorno virtual:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instala dependencias:
   ```
   pip install -r requirements.txt
   ```

3. Ejecuta migraciones:
   ```
   python manage.py migrate
   ```

4. Inicia el servidor en red local:
   ```
   python manage.py runserver 0.0.0.0:8000
   ```

Desde otras PC accede vía:
```
http://IP-LOCAL:8000
```
