BEGIN;

CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email VARCHAR(254) NOT NULL,
  password_hash TEXT NOT NULL,
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  phone VARCHAR(30),
  role VARCHAR(20) NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin')),
  status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'pending')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX users_email_unique ON users (LOWER(email));

CREATE TABLE addresses (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label VARCHAR(50) NOT NULL DEFAULT 'Principal',
  recipient_name VARCHAR(200) NOT NULL,
  recipient_phone VARCHAR(30) NOT NULL,
  address_line1 VARCHAR(220) NOT NULL,
  address_line2 VARCHAR(220),
  city VARCHAR(120) NOT NULL,
  state VARCHAR(120) NOT NULL,
  postal_code VARCHAR(20),
  country_code CHAR(2) NOT NULL DEFAULT 'CO',
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX addresses_one_default_per_user
  ON addresses(user_id) WHERE is_default;

CREATE TABLE brands (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  slug VARCHAR(140) NOT NULL UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE categories (
  id BIGSERIAL PRIMARY KEY,
  parent_id BIGINT REFERENCES categories(id) ON DELETE SET NULL,
  name VARCHAR(120) NOT NULL,
  slug VARCHAR(140) NOT NULL UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE products (
  id BIGSERIAL PRIMARY KEY,
  brand_id BIGINT REFERENCES brands(id) ON DELETE SET NULL,
  name VARCHAR(220) NOT NULL,
  slug VARCHAR(240) NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
  is_featured BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE product_categories (
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  category_id BIGINT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (product_id, category_id)
);

CREATE TABLE product_images (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL,
  alt_text VARCHAR(255) NOT NULL DEFAULT '',
  sort_order SMALLINT NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
  is_primary BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX product_images_one_primary
  ON product_images(product_id) WHERE is_primary;
CREATE UNIQUE INDEX product_images_product_url_unique
  ON product_images(product_id, image_url);

CREATE TABLE product_variants (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  sku VARCHAR(80) NOT NULL UNIQUE,
  size VARCHAR(30) NOT NULL,
  color_name VARCHAR(80) NOT NULL,
  color_hex CHAR(7),
  price_cop INTEGER NOT NULL CHECK (price_cop >= 0),
  compare_at_price_cop INTEGER CHECK (compare_at_price_cop IS NULL OR compare_at_price_cop >= price_cop),
  cost_cop INTEGER CHECK (cost_cop IS NULL OR cost_cop >= 0),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (product_id, size, color_name)
);

CREATE TABLE inventory (
  variant_id BIGINT PRIMARY KEY REFERENCES product_variants(id) ON DELETE CASCADE,
  stock_on_hand INTEGER NOT NULL DEFAULT 0 CHECK (stock_on_hand >= 0),
  stock_reserved INTEGER NOT NULL DEFAULT 0 CHECK (stock_reserved >= 0),
  stock_available INTEGER GENERATED ALWAYS AS (stock_on_hand - stock_reserved) STORED,
  low_stock_threshold INTEGER NOT NULL DEFAULT 3 CHECK (low_stock_threshold >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (stock_reserved <= stock_on_hand)
);

CREATE TABLE inventory_movements (
  id BIGSERIAL PRIMARY KEY,
  variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
  movement_type VARCHAR(30) NOT NULL CHECK (movement_type IN ('purchase', 'sale', 'return', 'adjustment', 'reservation', 'release')),
  quantity INTEGER NOT NULL CHECK (quantity <> 0),
  reference_type VARCHAR(40),
  reference_id BIGINT,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE carts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
  session_token VARCHAR(120),
  status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'converted', 'abandoned')),
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (user_id IS NOT NULL OR session_token IS NOT NULL)
);

CREATE UNIQUE INDEX carts_session_token_unique ON carts(session_token) WHERE session_token IS NOT NULL;
CREATE UNIQUE INDEX carts_one_active_per_user ON carts(user_id) WHERE status = 'active' AND user_id IS NOT NULL;

CREATE TABLE cart_items (
  id BIGSERIAL PRIMARY KEY,
  cart_id BIGINT NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
  variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cop INTEGER NOT NULL CHECK (unit_price_cop >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (cart_id, variant_id)
);

CREATE TABLE wishlists (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE wishlist_items (
  wishlist_id BIGINT NOT NULL REFERENCES wishlists(id) ON DELETE CASCADE,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (wishlist_id, product_id)
);

CREATE TABLE discount_codes (
  id BIGSERIAL PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  description VARCHAR(255),
  discount_type VARCHAR(20) NOT NULL CHECK (discount_type IN ('percentage', 'fixed')),
  discount_value INTEGER NOT NULL CHECK (discount_value > 0),
  minimum_order_cop INTEGER NOT NULL DEFAULT 0 CHECK (minimum_order_cop >= 0),
  maximum_discount_cop INTEGER CHECK (maximum_discount_cop IS NULL OR maximum_discount_cop > 0),
  usage_limit INTEGER CHECK (usage_limit IS NULL OR usage_limit > 0),
  usage_count INTEGER NOT NULL DEFAULT 0 CHECK (usage_count >= 0),
  starts_at TIMESTAMPTZ,
  ends_at TIMESTAMPTZ,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (discount_type <> 'percentage' OR discount_value <= 100),
  CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at)
);

CREATE TABLE shipping_methods (
  id BIGSERIAL PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  price_cop INTEGER NOT NULL DEFAULT 0 CHECK (price_cop >= 0),
  minimum_order_cop INTEGER NOT NULL DEFAULT 0 CHECK (minimum_order_cop >= 0),
  country_code CHAR(2) NOT NULL DEFAULT 'CO',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  order_number VARCHAR(30) NOT NULL UNIQUE,
  user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  customer_email VARCHAR(254) NOT NULL,
  status VARCHAR(25) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded')),
  payment_status VARCHAR(25) NOT NULL DEFAULT 'pending' CHECK (payment_status IN ('pending', 'authorized', 'paid', 'failed', 'refunded', 'partially_refunded')),
  fulfillment_status VARCHAR(25) NOT NULL DEFAULT 'unfulfilled' CHECK (fulfillment_status IN ('unfulfilled', 'preparing', 'shipped', 'delivered', 'returned')),
  subtotal_cop INTEGER NOT NULL CHECK (subtotal_cop >= 0),
  discount_cop INTEGER NOT NULL DEFAULT 0 CHECK (discount_cop >= 0),
  shipping_cop INTEGER NOT NULL DEFAULT 0 CHECK (shipping_cop >= 0),
  tax_cop INTEGER NOT NULL DEFAULT 0 CHECK (tax_cop >= 0),
  total_cop INTEGER GENERATED ALWAYS AS (subtotal_cop - discount_cop + shipping_cop + tax_cop) STORED,
  discount_code_id BIGINT REFERENCES discount_codes(id) ON DELETE SET NULL,
  shipping_address JSONB NOT NULL,
  billing_address JSONB NOT NULL,
  customer_note TEXT,
  placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (discount_cop <= subtotal_cop)
);

CREATE TABLE order_items (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  variant_id BIGINT REFERENCES product_variants(id) ON DELETE SET NULL,
  sku VARCHAR(80) NOT NULL,
  product_name VARCHAR(220) NOT NULL,
  variant_description VARCHAR(160) NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price_cop INTEGER NOT NULL CHECK (unit_price_cop >= 0),
  discount_cop INTEGER NOT NULL DEFAULT 0 CHECK (discount_cop >= 0),
  line_total_cop INTEGER GENERATED ALWAYS AS ((unit_price_cop * quantity) - discount_cop) STORED,
  CHECK (discount_cop <= unit_price_cop * quantity)
);

CREATE TABLE payments (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
  provider VARCHAR(50) NOT NULL,
  provider_reference VARCHAR(150),
  method VARCHAR(40) NOT NULL,
  amount_cop INTEGER NOT NULL CHECK (amount_cop > 0),
  status VARCHAR(25) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'authorized', 'paid', 'failed', 'refunded')),
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX payments_provider_reference_unique
  ON payments(provider, provider_reference) WHERE provider_reference IS NOT NULL;

CREATE TABLE shipments (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  carrier VARCHAR(100),
  tracking_number VARCHAR(120),
  status VARCHAR(25) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'preparing', 'shipped', 'in_transit', 'delivered', 'returned')),
  shipped_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX shipments_tracking_unique ON shipments(tracking_number) WHERE tracking_number IS NOT NULL;

CREATE TABLE reviews (
  id BIGSERIAL PRIMARY KEY,
  product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  order_item_id BIGINT REFERENCES order_items(id) ON DELETE SET NULL,
  rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  title VARCHAR(180),
  body TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'rejected')),
  is_verified_purchase BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, product_id)
);

CREATE INDEX product_variants_product_idx ON product_variants(product_id);
CREATE INDEX inventory_low_stock_idx ON inventory(stock_available, low_stock_threshold);
CREATE INDEX cart_items_cart_idx ON cart_items(cart_id);
CREATE INDEX orders_user_idx ON orders(user_id, placed_at DESC);
CREATE INDEX orders_status_idx ON orders(status, placed_at DESC);
CREATE INDEX order_items_order_idx ON order_items(order_id);
CREATE INDEX reviews_product_status_idx ON reviews(product_id, status, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
  table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'users', 'addresses', 'brands', 'categories', 'products',
    'product_variants', 'inventory', 'carts', 'cart_items',
    'wishlists', 'discount_codes', 'shipping_methods', 'orders', 'payments',
    'shipments', 'reviews'
  ]
  LOOP
    EXECUTE FORMAT(
      'CREATE TRIGGER %I_set_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
      table_name,
      table_name
    );
  END LOOP;
END;
$$;

COMMIT;
