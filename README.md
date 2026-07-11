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

Docker inicia PostgreSQL, ejecuta las migraciones, recopila los recursos estáticos y levanta Gunicorn en `http://127.0.0.1:8000/`.

## Funcionalidad

- Registro e inicio de sesión con usuario o correo.
- Vista de cuenta protegida.
- Carrito persistente para invitados y usuarios.
- Fusión automática del carrito invitado al iniciar sesión.
- Catálogo inicial administrable desde Django Admin.
