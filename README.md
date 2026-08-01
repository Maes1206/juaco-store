# Nexus Luxury Footwear

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

Los secretos del entorno local van en `.env.local` (ignorado por git); Docker sigue leyendo `.env`.

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

## Pagos con Bold

El checkout cobra en línea con el [botón de pagos de Bold](https://developers.bold.co/pagos-en-linea/boton-de-pagos). Si `BOLD_IDENTITY_KEY` o `BOLD_SECRET_KEY` están vacías, el método «Pago con Bold» no se ofrece y el resto del checkout sigue igual.

Flujo:

1. El comprador elige «Pago con Bold» y el pedido se crea en estado *Pendiente de pago* (el inventario queda reservado).
2. `/pago/<numero>/` firma el cobro en el servidor (SHA256 de `referencia + monto + moneda + llave secreta`) y abre la pasarela. La llave secreta nunca llega al navegador.
3. Bold devuelve al comprador a `/pago/bold/retorno/`. El estado de la URL solo sirve de pista: el pedido se actualiza consultando `GET /v2/payment-voucher/<referencia>`.
4. `/pago/bold/webhook/` recibe `SALE_APPROVED`, `SALE_REJECTED` y `VOID_APPROVED`, valida la cabecera `x-bold-signature` (HMAC-SHA256 del cuerpo en base64) y es idempotente ante reintentos. Una anulación cancela el pedido y devuelve el inventario.
5. Cada intento usa una referencia propia (`JS-20260801-0001-1`, `-2`, …): tras un rechazo el comprador puede reintentar.

Configuración:

| Variable | Uso |
| --- | --- |
| `BOLD_IDENTITY_KEY` | Llave de identidad; viaja al navegador y autentica la consulta de estado. |
| `BOLD_SECRET_KEY` | Llave secreta; solo firma cobros y valida webhooks. |
| `BOLD_TEST_MODE` | `1` con llaves de prueba. Solo cambia el aviso del checkout; no afecta la validación de firmas. |
| `BOLD_ALLOW_UNSIGNED_WEBHOOKS` | **Solo desarrollo.** El sandbox de Bold firma con llave vacía; aceptarla equivale a no validar la firma, así que con `1` cualquiera podría marcar un pedido como pagado. El servidor se niega a arrancar si lo activas sin `DJANGO_DEBUG=1`. |
| `BOLD_PUBLIC_BASE_URL` | Dominio HTTPS público para el retorno y el webhook. |

Bold exige HTTPS en la URL de retorno, así que en `http://localhost` no se envía: la página de pago ofrece «Ya pagué, verificar», que consulta la API y confirma el pedido. Para probar el retorno y el webhook en local, expón el puerto con un túnel HTTPS y pon esa URL en `BOLD_PUBLIC_BASE_URL`; registra `<dominio>/pago/bold/webhook/` en el panel de Bold.

Tarjetas del [ambiente de pruebas](https://developers.bold.co/pagos-en-linea/boton-de-pagos/ambiente-pruebas): `4111111111111111` aprueba, `4970110000000062` rechaza y `5204730000008404` falla. Las referencias de prueba expiran a las 12 horas.

## Producción

1. Copia `.env.example` a `.env` y reemplaza todas las claves marcadas con `CAMBIA`.
2. Configura `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` y `BOLD_PUBLIC_BASE_URL` con el dominio HTTPS real, y cambia las llaves de Bold por las de producción.
3. Publica el contenedor detrás de un proxy TLS que envíe `X-Forwarded-Proto: https`.
4. Ejecuta `docker compose -f docker-compose.yml up -d --build`; así se omite el archivo local `docker-compose.override.yml`, se usa Gunicorn y el arranque aplica migraciones y recopila estáticos.
5. Comprueba el estado con `docker compose ps` y los logs con `docker compose logs -f web`.

Los valores por defecto asumen producción: sin `DJANGO_DEBUG` el sitio arranca en modo seguro, y sin `DJANGO_SECRET_KEY` propia no arranca en absoluto. `.env.local` (usado por `runserver`) nunca entra en la imagen de Docker.

### Permisos del panel `/panel-admin/`

`is_staff` abre el panel, pero cada sección exige su permiso: `store.view_order` para Ventas y Reportes, `auth.view_user` + `store.view_customerprofile` para Clientes, `store.view_contactrequest` para Marketing, `store.view_product` para Productos y `store.view_blogpost` para Blog. Las secciones sin permiso no aparecen en el menú, no se consultan en la base de datos y redirigen al Resumen si se piden por URL. Así una cuenta creada para moderar el blog no accede a cédulas, direcciones ni ventas.

### Bloqueo de inicio de sesión

[django-axes](https://github.com/jazzband/django-axes) bloquea el acceso tras `AXES_FAILURE_LIMIT` (5 por defecto) contraseñas incorrectas seguidas para el mismo usuario **desde la misma IP**; se bloquea solo por IP dejaría fuera a cualquier otra persona en la misma red (oficina, wifi compartido) apenas alguien fallara varias veces. El bloqueo se levanta solo tras `AXES_COOLOFF_MINUTES` (15 por defecto); seguir insistiendo durante ese tiempo no lo extiende. Aplica igual al login de la tienda y al de `/admin/`. Se desactiva automáticamente al correr `manage.py test`.

La ruta `/healthz/` está disponible para health checks. La base PostgreSQL usa un volumen persistente; configura además copias de seguridad externas del volumen.
