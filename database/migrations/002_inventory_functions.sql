BEGIN;

CREATE OR REPLACE FUNCTION reserve_inventory(
  p_variant_id BIGINT,
  p_quantity INTEGER,
  p_reference_type VARCHAR DEFAULT 'cart',
  p_reference_id BIGINT DEFAULT NULL
)
RETURNS TABLE (variant_id BIGINT, stock_on_hand INTEGER, stock_reserved INTEGER, stock_available INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
  current_inventory inventory%ROWTYPE;
BEGIN
  IF p_quantity <= 0 THEN
    RAISE EXCEPTION 'La cantidad a reservar debe ser mayor que cero';
  END IF;

  SELECT * INTO current_inventory
  FROM inventory i
  WHERE i.variant_id = p_variant_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'No existe inventario para la variante %', p_variant_id;
  END IF;

  IF current_inventory.stock_available < p_quantity THEN
    RAISE EXCEPTION 'Inventario insuficiente. Disponible: %, solicitado: %', current_inventory.stock_available, p_quantity;
  END IF;

  UPDATE inventory i
  SET stock_reserved = i.stock_reserved + p_quantity
  WHERE i.variant_id = p_variant_id
  RETURNING i.* INTO current_inventory;

  INSERT INTO inventory_movements (variant_id, movement_type, quantity, reference_type, reference_id)
  VALUES (p_variant_id, 'reservation', -p_quantity, p_reference_type, p_reference_id);

  RETURN QUERY SELECT
    current_inventory.variant_id,
    current_inventory.stock_on_hand,
    current_inventory.stock_reserved,
    current_inventory.stock_available;
END;
$$;

CREATE OR REPLACE FUNCTION release_inventory(
  p_variant_id BIGINT,
  p_quantity INTEGER,
  p_reference_type VARCHAR DEFAULT 'cart',
  p_reference_id BIGINT DEFAULT NULL
)
RETURNS TABLE (variant_id BIGINT, stock_on_hand INTEGER, stock_reserved INTEGER, stock_available INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
  current_inventory inventory%ROWTYPE;
BEGIN
  IF p_quantity <= 0 THEN
    RAISE EXCEPTION 'La cantidad a liberar debe ser mayor que cero';
  END IF;

  SELECT * INTO current_inventory
  FROM inventory i
  WHERE i.variant_id = p_variant_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'No existe inventario para la variante %', p_variant_id;
  END IF;

  IF current_inventory.stock_reserved < p_quantity THEN
    RAISE EXCEPTION 'La cantidad reservada es menor que la cantidad a liberar';
  END IF;

  UPDATE inventory i
  SET stock_reserved = i.stock_reserved - p_quantity
  WHERE i.variant_id = p_variant_id
  RETURNING i.* INTO current_inventory;

  INSERT INTO inventory_movements (variant_id, movement_type, quantity, reference_type, reference_id)
  VALUES (p_variant_id, 'release', p_quantity, p_reference_type, p_reference_id);

  RETURN QUERY SELECT
    current_inventory.variant_id,
    current_inventory.stock_on_hand,
    current_inventory.stock_reserved,
    current_inventory.stock_available;
END;
$$;

CREATE OR REPLACE FUNCTION complete_inventory_sale(
  p_variant_id BIGINT,
  p_quantity INTEGER,
  p_order_id BIGINT
)
RETURNS TABLE (variant_id BIGINT, stock_on_hand INTEGER, stock_reserved INTEGER, stock_available INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
  current_inventory inventory%ROWTYPE;
BEGIN
  IF p_quantity <= 0 THEN
    RAISE EXCEPTION 'La cantidad vendida debe ser mayor que cero';
  END IF;

  SELECT * INTO current_inventory
  FROM inventory i
  WHERE i.variant_id = p_variant_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'No existe inventario para la variante %', p_variant_id;
  END IF;

  IF current_inventory.stock_reserved < p_quantity THEN
    RAISE EXCEPTION 'La venta requiere una reserva previa suficiente';
  END IF;

  UPDATE inventory i
  SET
    stock_on_hand = i.stock_on_hand - p_quantity,
    stock_reserved = i.stock_reserved - p_quantity
  WHERE i.variant_id = p_variant_id
  RETURNING i.* INTO current_inventory;

  INSERT INTO inventory_movements (variant_id, movement_type, quantity, reference_type, reference_id)
  VALUES (p_variant_id, 'sale', -p_quantity, 'order', p_order_id);

  RETURN QUERY SELECT
    current_inventory.variant_id,
    current_inventory.stock_on_hand,
    current_inventory.stock_reserved,
    current_inventory.stock_available;
END;
$$;

COMMIT;
