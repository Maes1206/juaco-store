# Juaco Store

Ecommerce de sneakers migrado a Django con autenticación, catálogo y carrito persistente.

## Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

La aplicación queda disponible en `http://127.0.0.1:8000/`.

## Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Docker inicia PostgreSQL, ejecuta las migraciones y deja la aplicación en `http://127.0.0.1:8000/`. La configuración de desarrollo monta el proyecto dentro del contenedor y usa la recarga automática de Django, por lo que los cambios en Python, plantillas y CSS se ven sin reconstruir la imagen.

## Funcionalidad

- Registro e inicio de sesión con usuario o correo.
- Vista de cuenta protegida.
- Carrito persistente para invitados y usuarios.
- Fusión automática del carrito invitado al iniciar sesión.
- Catálogo inicial administrable desde Django Admin.
- Favoritos persistentes por usuario, con movimiento al carrito.

## Producción

1. Copia `.env.example` a `.env` y reemplaza todas las claves marcadas con `CAMBIA`.
2. Configura `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS` con el dominio HTTPS real.
3. Publica el contenedor detrás de un proxy TLS que envíe `X-Forwarded-Proto: https`.
4. Ejecuta `docker compose -f docker-compose.yml up -d --build`; así se omite el archivo local `docker-compose.override.yml`, se usa Gunicorn y el arranque aplica migraciones y recopila estáticos.
5. Comprueba el estado con `docker compose ps` y los logs con `docker compose logs -f web`.

La ruta `/healthz/` está disponible para health checks. La base PostgreSQL usa un volumen persistente; configura además copias de seguridad externas del volumen.
