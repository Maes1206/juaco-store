-- Consulta reutilizable para que la API filtre el catálogo en PostgreSQL.
-- Los límites y filtros se reciben como parámetros, nunca como SQL concatenado.
CREATE OR REPLACE FUNCTION catalog_products(
  p_brand_slug TEXT DEFAULT NULL,
  p_min_price_cop INTEGER DEFAULT NULL,
  p_max_price_cop INTEGER DEFAULT NULL,
  p_size TEXT DEFAULT NULL
)
RETURNS TABLE (
  product_id BIGINT,
  slug VARCHAR,
  name VARCHAR,
  brand_name VARCHAR,
  image_url TEXT,
  price_cop INTEGER,
  available_sizes TEXT[]
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.slug,
    p.name,
    b.name,
    image.image_url,
    MIN(v.price_cop)::INTEGER AS price_cop,
    ARRAY_AGG(DISTINCT v.size ORDER BY v.size) AS available_sizes
  FROM products p
  JOIN brands b ON b.id = p.brand_id
  JOIN product_variants v ON v.product_id = p.id AND v.is_active = TRUE
  JOIN inventory i ON i.variant_id = v.id AND i.stock_available > 0
  LEFT JOIN LATERAL (
    SELECT pi.image_url
    FROM product_images pi
    WHERE pi.product_id = p.id
    ORDER BY pi.is_primary DESC, pi.sort_order ASC
    LIMIT 1
  ) image ON TRUE
  WHERE p.status = 'active'
    AND (p_brand_slug IS NULL OR b.slug = p_brand_slug)
    AND (p_size IS NULL OR v.size = p_size)
  GROUP BY p.id, p.slug, p.name, b.name, image.image_url
  HAVING (p_min_price_cop IS NULL OR MIN(v.price_cop) >= p_min_price_cop)
     AND (p_max_price_cop IS NULL OR MIN(v.price_cop) <= p_max_price_cop)
  ORDER BY MIN(v.price_cop) ASC, p.name ASC;
$$;

-- Ejemplo de uso desde la futura API:
-- SELECT * FROM catalog_products('jordan', 230000, 300000, '40');
