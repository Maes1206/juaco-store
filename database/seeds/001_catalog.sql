BEGIN;

INSERT INTO brands (name, slug) VALUES
  ('Nike', 'nike'),
  ('Jordan', 'jordan'),
  ('Adidas', 'adidas')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO categories (name, slug) VALUES
  ('Sneakers', 'sneakers'),
  ('Hombre', 'hombre'),
  ('Mujer', 'mujer'),
  ('Clásicas', 'clasicas'),
  ('Ediciones especiales', 'ediciones-especiales')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO products (brand_id, name, slug, description, status, is_featured)
SELECT
  b.id,
  source.name,
  source.slug,
  source.description,
  'active',
  source.is_featured
FROM (VALUES
  ('nike', 'Nike SB Dunk Low x Travis Scott “Cactus Jack”', 'nike-sb-dunk-low-travis-scott-cactus-jack', 'Sneaker urbano de edición especial con materiales premium y diseño icónico.', TRUE),
  ('adidas', 'Adidas Forum Low Verde/Blanco', 'adidas-forum-low-verde-blanco', 'Silueta retro con detalles verdes y blancos para uso diario.', TRUE),
  ('jordan', 'Air Jordan 4 Retro SE Paris Olympics', 'air-jordan-4-retro-se-paris-olympics', 'Diseño inspirado en París con una construcción resistente y cómoda.', TRUE),
  ('jordan', 'Air Jordan 4 Retro Military Black', 'air-jordan-4-retro-military-black', 'Combinación clásica en blanco, negro y gris con amortiguación Air.', FALSE),
  ('jordan', 'Air Jordan 3 Retro White Cobalt Bliss', 'air-jordan-3-retro-white-cobalt-bliss', 'Jordan 3 en tonos claros con detalles Cobalt Bliss.', TRUE),
  ('jordan', 'Jordan 1 Obsidian', 'jordan-1-obsidian', 'Silueta Jordan 1 de corte alto en azul obsidiana.', TRUE),
  ('jordan', 'Jordan 4 J Balvin', 'jordan-4-j-balvin', 'Edición especial con una paleta vibrante y acabados premium.', FALSE),
  ('nike', 'Nike Air Force 1 Triple White', 'nike-air-force-1-triple-white', 'Un clásico completamente blanco, versátil y fácil de combinar.', TRUE)
) AS source(brand_slug, name, slug, description, is_featured)
JOIN brands b ON b.slug = source.brand_slug
ON CONFLICT (slug) DO UPDATE SET
  brand_id = EXCLUDED.brand_id,
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  status = EXCLUDED.status,
  is_featured = EXCLUDED.is_featured,
  updated_at = NOW();

INSERT INTO product_categories (product_id, category_id)
SELECT p.id, c.id
FROM (VALUES
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'sneakers'),
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'ediciones-especiales'),
  ('adidas-forum-low-verde-blanco', 'sneakers'),
  ('adidas-forum-low-verde-blanco', 'clasicas'),
  ('air-jordan-4-retro-se-paris-olympics', 'sneakers'),
  ('air-jordan-4-retro-se-paris-olympics', 'ediciones-especiales'),
  ('air-jordan-4-retro-military-black', 'sneakers'),
  ('air-jordan-3-retro-white-cobalt-bliss', 'sneakers'),
  ('jordan-1-obsidian', 'sneakers'),
  ('jordan-4-j-balvin', 'ediciones-especiales'),
  ('nike-air-force-1-triple-white', 'clasicas')
) AS source(product_slug, category_slug)
JOIN products p ON p.slug = source.product_slug
JOIN categories c ON c.slug = source.category_slug
ON CONFLICT DO NOTHING;

INSERT INTO product_categories (product_id, category_id)
SELECT p.id, c.id
FROM products p
CROSS JOIN categories c
WHERE c.slug IN ('hombre', 'mujer')
ON CONFLICT DO NOTHING;

INSERT INTO product_images (product_id, image_url, alt_text, sort_order, is_primary)
SELECT p.id, source.image_url, source.alt_text, 0, TRUE
FROM (VALUES
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'assets/img/shop/541x540/8743.png', 'Nike SB Dunk Low x Travis Scott Cactus Jack'),
  ('adidas-forum-low-verde-blanco', 'assets/img/shop/727340.png', 'Adidas Forum Low verde y blanco'),
  ('air-jordan-4-retro-se-paris-olympics', 'assets/img/shop/jordan423.png', 'Air Jordan 4 Retro SE Paris Olympics'),
  ('air-jordan-4-retro-military-black', 'assets/img/shop/jodan421.png', 'Air Jordan 4 Retro Military Black'),
  ('air-jordan-3-retro-white-cobalt-bliss', 'assets/img/shop/jordan623.png', 'Air Jordan 3 Retro White Cobalt Bliss'),
  ('jordan-1-obsidian', 'assets/img/shop/jordanobsidian-card.png', 'Jordan 1 Obsidian'),
  ('jordan-4-j-balvin', 'assets/img/shop/2634.png', 'Jordan 4 J Balvin'),
  ('nike-air-force-1-triple-white', 'assets/img/shop/Sin título (270 x 274 px) (3).png', 'Nike Air Force 1 Triple White')
) AS source(product_slug, image_url, alt_text)
JOIN products p ON p.slug = source.product_slug
ON CONFLICT DO NOTHING;

INSERT INTO product_images (product_id, image_url, alt_text, sort_order, is_primary)
SELECT p.id, source.image_url, source.alt_text, source.sort_order, FALSE
FROM (VALUES
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'assets/img/shop/541x540/823763.png', 'Suela Nike SB Dunk Low x Travis Scott Cactus Jack', 1),
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'assets/img/shop/541x540/8276.png', 'Vista frontal Nike SB Dunk Low x Travis Scott Cactus Jack', 2),
  ('nike-sb-dunk-low-travis-scott-cactus-jack', 'assets/img/shop/541x540/7173.png', 'Vista posterior Nike SB Dunk Low x Travis Scott Cactus Jack', 3)
) AS source(product_slug, image_url, alt_text, sort_order)
JOIN products p ON p.slug = source.product_slug
ON CONFLICT DO NOTHING;

WITH catalog(product_slug, sku_prefix, color_name, color_hex, price_cop, compare_at_price_cop) AS (
  VALUES
    ('nike-sb-dunk-low-travis-scott-cactus-jack', 'JS-NK-TS', 'Café/Verde', '#69513A', 260000, 300000),
    ('adidas-forum-low-verde-blanco', 'JS-AD-FL', 'Verde/Blanco', '#28533C', 190000, NULL),
    ('air-jordan-4-retro-se-paris-olympics', 'JS-JD-PAR', 'Gris', '#666666', 241000, 267778),
    ('air-jordan-4-retro-military-black', 'JS-JD-MB', 'Blanco/Negro', '#E7E7E7', 240000, NULL),
    ('air-jordan-3-retro-white-cobalt-bliss', 'JS-JD-CB', 'Blanco/Azul', '#DCE7EE', 230000, 255556),
    ('jordan-1-obsidian', 'JS-JD-OB', 'Azul Obsidiana', '#183654', 240000, NULL),
    ('jordan-4-j-balvin', 'JS-JD-JB', 'Beige/Naranja', '#D7B98E', 450000, NULL),
    ('nike-air-force-1-triple-white', 'JS-NK-AF1', 'Blanco', '#FFFFFF', 230000, 400000)
), sizes(size) AS (
  VALUES ('38'), ('40'), ('42'), ('44')
)
INSERT INTO product_variants (
  product_id,
  sku,
  size,
  color_name,
  color_hex,
  price_cop,
  compare_at_price_cop
)
SELECT
  p.id,
  catalog.sku_prefix || '-' || sizes.size,
  sizes.size,
  catalog.color_name,
  catalog.color_hex,
  catalog.price_cop,
  catalog.compare_at_price_cop
FROM catalog
JOIN products p ON p.slug = catalog.product_slug
CROSS JOIN sizes
ON CONFLICT (sku) DO UPDATE SET
  price_cop = EXCLUDED.price_cop,
  compare_at_price_cop = EXCLUDED.compare_at_price_cop,
  is_active = TRUE,
  updated_at = NOW();

INSERT INTO inventory (variant_id, stock_on_hand, stock_reserved, low_stock_threshold)
SELECT id, 6, 0, 2
FROM product_variants
ON CONFLICT (variant_id) DO NOTHING;

INSERT INTO shipping_methods (code, name, price_cop, minimum_order_cop) VALUES
  ('standard-co', 'Envío nacional', 15000, 0),
  ('free-co', 'Envío gratis', 0, 400001),
  ('local-pickup', 'Recogida local', 0, 0)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  price_cop = EXCLUDED.price_cop,
  minimum_order_cop = EXCLUDED.minimum_order_cop,
  is_active = TRUE,
  updated_at = NOW();

INSERT INTO discount_codes (
  code,
  description,
  discount_type,
  discount_value,
  minimum_order_cop,
  maximum_discount_cop,
  usage_limit,
  is_active
) VALUES (
  'BIENVENIDO10',
  '10% de descuento para la primera compra',
  'percentage',
  10,
  150000,
  50000,
  500,
  TRUE
)
ON CONFLICT (code) DO UPDATE SET
  description = EXCLUDED.description,
  discount_value = EXCLUDED.discount_value,
  minimum_order_cop = EXCLUDED.minimum_order_cop,
  maximum_discount_cop = EXCLUDED.maximum_discount_cop,
  usage_limit = EXCLUDED.usage_limit,
  is_active = TRUE,
  updated_at = NOW();

COMMIT;
