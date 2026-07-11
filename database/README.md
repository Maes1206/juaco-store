# Base de datos de Juaco Store

La base inicial usa PostgreSQL 16 y almacena valores monetarios como enteros en pesos colombianos. Por ejemplo, `260000` representa `$260.000 COP`.

## Módulos incluidos

- Usuarios, roles y direcciones.
- Marcas, categorías, productos, imágenes y variantes por talla/color.
- Inventario disponible, reservado y movimientos de inventario.
- Carritos de usuarios o invitados y sus productos.
- Favoritos.
- Códigos de descuento.
- Métodos de envío, incluida la regla de envío gratis para compras superiores a `$400.000 COP`.
- Pedidos y líneas de pedido con datos históricos del producto.
- Pagos, envíos, seguimiento y reseñas verificadas.

## Iniciar localmente

1. Copia `.env.example` como `.env` y cambia la contraseña.
2. Ejecuta:

```bash
docker compose up -d
```

En el primer inicio, PostgreSQL ejecuta automáticamente:

1. `database/migrations/001_initial_schema.sql`
2. `database/migrations/002_inventory_functions.sql`
3. `database/seeds/001_catalog.sql`

El catálogo inicial contiene los productos e imágenes que ya usa el frontend.

Las funciones `reserve_inventory`, `release_inventory` y `complete_inventory_sale` actualizan existencias de forma atómica y evitan vender más unidades de las disponibles.

## Conexión local

```text
Host: localhost
Puerto: 5432
Base: juaco_store
Usuario: juaco
Contraseña: la definida en .env
```

Cadena de conexión para una futura API:

```text
postgresql://juaco:TU_CLAVE@localhost:5432/juaco_store
```

## Comprobaciones útiles

### Filtro de catálogo por precio

La función `catalog_products` aplica marca, talla y rango de precio sobre variantes activas con inventario disponible. La API debe pasar los valores como parámetros preparados:

```sql
SELECT * FROM catalog_products('jordan', 230000, 300000, '40');
```

En una base que ya exista, aplica la nueva función una sola vez con:

```bash
docker compose exec -T db psql -U juaco -d juaco_store -f /docker-entrypoint-initdb.d/04-catalog-price-filter.sql
```

```sql
SELECT p.name, v.sku, v.size, v.price_cop, i.stock_available
FROM products p
JOIN product_variants v ON v.product_id = p.id
JOIN inventory i ON i.variant_id = v.id
WHERE p.status = 'active'
ORDER BY p.name, v.size;
```

```sql
SELECT name, price_cop, minimum_order_cop
FROM shipping_methods
WHERE is_active = TRUE
ORDER BY minimum_order_cop;
```

## Siguiente etapa

La próxima capa debe ser una API que concentre las transacciones de carrito, reserva de inventario, creación de pedidos y confirmación de pagos. El frontend no debe conectarse directamente a PostgreSQL ni calcular inventario o precios finales por sí solo.
