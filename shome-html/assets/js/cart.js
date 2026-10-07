/* Carrito persistente respaldado por Django. */
(function () {
  'use strict';

  function csrfToken() {
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function money(value) {
    return '$' + Number(value || 0).toLocaleString('es-CO') + ' COP';
  }

  function request(url, options) {
    options = options || {};
    options.headers = Object.assign({
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken()
    }, options.headers || {});
    return fetch(url, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || 'No fue posible completar la acción.');
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function productIdFrom(trigger) {
    if (trigger.dataset.productId) return trigger.dataset.productId;
    var current = new URLSearchParams(window.location.search).get('producto');
    if (current && trigger.closest('.product-single-item')) return current;
    var card = trigger.closest('.product-item, .catalog-product');
    var detailLink = card && card.querySelector('a[href*="single-product.html?producto="]');
    return detailLink ? new URL(detailLink.href, window.location.href).searchParams.get('producto') : '';
  }

  function selectedSize(trigger) {
    var detail = trigger.closest('.product-single-item');
    var active = detail && detail.querySelector('.product-size .size-list li.active');
    return active ? active.textContent.trim() : '';
  }

  function selectedColor(trigger) {
    var detail = trigger.closest('.product-single-item');
    var active = detail && detail.querySelector('.product-color .color-list li.active');
    return active ? (active.dataset.color || active.getAttribute('aria-label') || '').trim() : '';
  }

  var variantInventory = [];
  var variantInventoryNode = document.getElementById('product-variant-inventory');
  if (variantInventoryNode) {
    try { variantInventory = JSON.parse(variantInventoryNode.textContent || '[]'); }
    catch (error) { variantInventory = []; }
  }

  function selectedVariant(trigger) {
    if (!variantInventory.length) return null;
    var size = selectedSize(trigger);
    var color = selectedColor(trigger);
    return variantInventory.find(function (variant) {
      return variant.active && variant.size === size && variant.color === color;
    }) || null;
  }

  function activateVariantOption(option) {
    if (!option || !option.parentElement) return;
    option.parentElement.querySelectorAll('li').forEach(function (item) {
      var active = item === option;
      item.classList.toggle('active', active);
      item.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function reconcileVariantSelection(detail, changedOption) {
    if (!detail || !variantInventory.length) return;
    var current = selectedVariant(detail);
    if (current && current.active && Number(current.stock || 0) > 0) return;

    var candidates = variantInventory.filter(function (entry) {
      if (!entry.active || Number(entry.stock || 0) < 1) return false;
      if (changedOption && changedOption.dataset.size) return entry.size === changedOption.dataset.size;
      if (changedOption && changedOption.dataset.color) return entry.color === changedOption.dataset.color;
      return true;
    });
    var replacement = candidates[0];
    if (!replacement) return;
    activateVariantOption(detail.querySelector('.size-list li[data-size="' + CSS.escape(replacement.size) + '"]'));
    activateVariantOption(detail.querySelector('.color-list li[data-color="' + CSS.escape(replacement.color) + '"]'));
  }

  function updateVariantAvailability(detail) {
    if (!detail || !variantInventory.length) return;
    var variant = selectedVariant(detail);
    var stock = variant ? Number(variant.stock || 0) : 0;
    var status = detail.querySelector('.product-stock-status');
    var addButton = detail.querySelector('[data-add-to-cart]');
    if (status) {
      status.classList.toggle('is-out', stock < 1);
      status.innerHTML = stock > 0
        ? '<i class="fa fa-check-circle"></i> Disponible · ' + stock + (stock === 1 ? ' unidad' : ' unidades')
        : '<i class="fa fa-times-circle"></i> Combinación agotada';
    }
    if (addButton) {
      addButton.setAttribute('aria-disabled', stock > 0 ? 'false' : 'true');
      addButton.classList.toggle('is-disabled', stock < 1);
    }

    detail.querySelectorAll('.size-list li[data-size]').forEach(function (option) {
      var available = variantInventory.some(function (entry) {
        return entry.active && entry.stock > 0 && entry.size === option.dataset.size;
      });
      option.classList.toggle('is-unavailable', !available);
      option.setAttribute('aria-disabled', available ? 'false' : 'true');
    });
    detail.querySelectorAll('.color-list li[data-color]').forEach(function (option) {
      var available = variantInventory.some(function (entry) {
        return entry.active && entry.stock > 0 && entry.color === option.dataset.color;
      });
      option.classList.toggle('is-unavailable', !available);
      option.setAttribute('aria-disabled', available ? 'false' : 'true');
    });
  }

  function updateBadges(cart) {
    document.querySelectorAll('.shop-count').forEach(function (badge) {
      badge.textContent = String(cart.count);
      badge.setAttribute('aria-label', cart.count === 1 ? '1 artículo en el carrito' : cart.count + ' artículos en el carrito');
    });
  }

  function escapeHtml(value) {
    var node = document.createElement('div');
    node.textContent = String(value == null ? '' : value);
    return node.innerHTML;
  }

  function asideCartItem(item) {
    var productUrl = 'single-product.html?producto=' + encodeURIComponent(item.product_id);
    return '<li class="product-list-item">' +
      '<a href="#" class="remove" data-cart-remove="' + item.id + '" aria-label="Eliminar ' + escapeHtml(item.name) + '">×</a>' +
      '<a href="' + productUrl + '">' +
        '<img src="' + escapeHtml(item.image) + '" width="90" height="110" alt="' + escapeHtml(item.name) + '">' +
        '<span class="product-title">' + escapeHtml(item.name) + '</span>' +
      '</a>' +
      (item.size ? '<span class="product-size">Talla: ' + escapeHtml(item.size) + '</span>' : '') +
      (item.color ? '<span class="product-size">Color: ' + escapeHtml(item.color) + '</span>' : '') +
      '<span class="product-price">' + item.quantity + ' × ' + money(item.price) + '</span>' +
    '</li>';
  }

  function cartRow(item) {
    return '<tr class="cart-product-item" data-cart-row="' + item.id + '">' +
      '<td class="product-remove"><a href="#" data-cart-remove="' + item.id + '" aria-label="Eliminar producto"><i class="fa fa-trash-o"></i></a></td>' +
      '<td class="product-thumb"><a href="single-product.html?producto=' + encodeURIComponent(item.product_id) + '"><img src="' + item.image + '" width="90" height="110" alt="' + item.name + '"></a></td>' +
      '<td class="product-name"><h4 class="title"><a href="single-product.html?producto=' + encodeURIComponent(item.product_id) + '">' + item.name + '</a></h4>' + (item.size ? '<small>Talla: ' + item.size + '</small>' : '') + (item.color ? '<small>Color: ' + item.color + '</small>' : '') + '</td>' +
      '<td class="product-price"><span class="price">' + money(item.price) + '</span></td>' +
      '<td class="product-quantity"><div class="pro-qty"><input type="number" min="1" class="quantity" data-cart-quantity="' + item.id + '" value="' + item.quantity + '"></div></td>' +
      '<td class="product-subtotal"><span class="price">' + money(item.subtotal) + '</span></td></tr>';
  }

  function renderCart(cart) {
    updateBadges(cart);
    var weightInput = document.querySelector('[data-auto-shipping-weight-input]');
    if (weightInput) {
      var nextWeight = String(cart.estimated_weight || 0.1);
      var weightChanged = Number(weightInput.value) !== Number(nextWeight);
      weightInput.value = nextWeight;
      document.querySelectorAll('[data-auto-shipping-weight]').forEach(function (node) {
        node.textContent = Number(nextWeight).toLocaleString('es-CO', { maximumFractionDigits: 2 });
      });
      if (weightChanged) document.dispatchEvent(new CustomEvent('cart:weight-updated'));
    }
    document.querySelectorAll('.aside-cart-product-list').forEach(function (list) {
      list.innerHTML = cart.items.length
        ? cart.items.map(asideCartItem).join('')
        : '<li class="cart-empty-message">Tu carrito está vacío. <a href="shop.html">Explorar productos</a></li>';
    });
    var body = document.getElementById('django-cart-items');
    if (body) {
      body.innerHTML = cart.items.length ? cart.items.map(cartRow).join('') +
        '<tr class="actions"><td class="border-0" colspan="6"><button type="button" class="clear-cart">Vaciar carrito</button><a href="shop.html" class="btn-theme btn-flat">Seguir comprando</a></td></tr>' :
        '<tr class="cart-empty-row"><td colspan="6">Tu carrito está vacío. <a href="shop.html">Explorar productos</a></td></tr>';
    }
    document.querySelectorAll('.cart-subtotal .price, [data-cart-subtotal]').forEach(function (node) {
      node.textContent = money(cart.subtotal);
    });
    document.querySelectorAll('[data-cart-shipping]').forEach(function (node) {
      var isFree = cart.shipping === 0 && cart.count > 0;
      node.textContent = isFree ? 'GRATIS' : money(cart.shipping);
      node.classList.toggle('is-free', isFree);
    });
    document.querySelectorAll('[data-free-shipping-callout]').forEach(function (callout) {
      var unlocked = Boolean(cart.free_shipping_unlocked && cart.count > 0);
      var remaining = Number(cart.free_shipping_remaining || 0);
      var progress = Math.max(0, Math.min(100, Number(cart.free_shipping_progress || 0)));
      callout.classList.toggle('is-unlocked', unlocked);

      var title = callout.querySelector('[data-free-shipping-title]');
      var message = callout.querySelector('[data-free-shipping-message]');
      var badge = callout.querySelector('[data-free-shipping-badge]');
      var icon = callout.querySelector('[data-free-shipping-icon]');
      var progressRoot = callout.querySelector('[data-free-shipping-progress]');
      var progressBar = callout.querySelector('[data-free-shipping-progress-bar]');
      var action = callout.querySelector('[data-free-shipping-action]');

      if (title) title.textContent = unlocked ? '¡Envío gratis desbloqueado!' : 'Estás cerca del envío gratis';
      if (message) message.textContent = unlocked
        ? 'Ahorras el costo del envío en esta compra.'
        : 'Agrega ' + money(remaining) + ' más a tu carrito y recíbelo gratis.';
      if (badge) badge.textContent = unlocked ? 'ACTIVO' : 'META ' + money(cart.free_shipping_threshold);
      if (icon) {
        icon.classList.toggle('fa-check', unlocked);
        icon.classList.toggle('fa-truck', !unlocked);
      }
      if (progressRoot) progressRoot.setAttribute('aria-valuenow', String(progress));
      if (progressBar) progressBar.style.width = progress + '%';
      if (action) action.hidden = unlocked;
    });
    document.querySelectorAll('.order-total .price').forEach(function (node) {
      node.textContent = money(cart.total);
    });
    document.querySelectorAll('.cart-discount').forEach(function (row) {
      row.hidden = !cart.discount;
    });
    document.querySelectorAll('[data-cart-discount]').forEach(function (node) {
      node.textContent = '-' + money(cart.discount);
    });
    document.querySelectorAll('[data-coupon-code]').forEach(function (node) {
      node.textContent = cart.coupon_code ? '(' + cart.coupon_code + ')' : '';
    });
    document.querySelectorAll('.aside-cart-wrapper .cart-total .amount').forEach(function (node) {
      node.textContent = money(cart.subtotal);
    });
    window.JuacoCartState = cart;
    document.dispatchEvent(new CustomEvent('cart:rendered', { detail: cart }));
  }

  function notify(message, isError) {
    var toast = document.createElement('div');
    toast.className = 'product-share-feedback' + (isError ? ' is-error' : '');
    toast.textContent = message;
    document.body.appendChild(toast);
    window.setTimeout(function () { toast.classList.add('is-visible'); }, 10);
    window.setTimeout(function () { toast.remove(); }, 2400);
  }

  document.addEventListener('click', function (event) {
    var variantOption = event.target.closest('.product-size .size-list li, .product-color .color-list li');
    if (variantOption && variantOption.getAttribute('aria-disabled') === 'true') {
      event.preventDefault();
      event.stopImmediatePropagation();
      notify('Esta combinación está agotada.', true);
      return;
    }
    var favoriteTrigger = event.target.closest('[data-favorite-product], .btn-product-wishlist, .product-wishlist-compare a[href="shop-wishlist.html"]');
    if (favoriteTrigger) {
      var favoriteProductId = productIdFrom(favoriteTrigger);
      if (!favoriteProductId) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      request('/api/favorites/', {
        method: 'POST',
        body: JSON.stringify({ product_id: favoriteProductId })
      }).then(function () {
        favoriteTrigger.classList.add('is-favorite');
        notify('Producto guardado en favoritos.');
      }).catch(function (error) {
        if (error.status === 401) {
          window.location.href = '/account-login.html?next=' + encodeURIComponent(window.location.pathname + window.location.search);
          return;
        }
        notify(error.message, true);
      });
      return;
    }

    var favoriteRemove = event.target.closest('[data-favorite-remove]');
    if (favoriteRemove) {
      event.preventDefault();
      request('/api/favorites/' + favoriteRemove.dataset.favoriteRemove + '/', { method: 'DELETE' })
        .then(function () { window.location.reload(); })
        .catch(function (error) { notify(error.message, true); });
      return;
    }

    var favoriteMove = event.target.closest('[data-favorite-move]');
    if (favoriteMove) {
      event.preventDefault();
      request('/api/favorites/' + favoriteMove.dataset.favoriteMove + '/move-to-cart/', { method: 'POST' })
        .then(function (data) {
          renderCart(data.cart);
          notify('Producto agregado al carrito.');
          window.setTimeout(function () { window.location.reload(); }, 500);
        }).catch(function (error) { notify(error.message, true); });
      return;
    }

    var add = event.target.closest('[data-add-to-cart], .btn-product-cart, .product-single-item .btn-theme[href="shop-cart.html"]');
    if (add) {
      var productId = productIdFrom(add);
      if (!productId) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      var chosenVariant = selectedVariant(add);
      if (variantInventory.length && (!chosenVariant || Number(chosenVariant.stock || 0) < 1)) {
        notify('Selecciona una combinación disponible.', true);
        return;
      }
      request('/api/cart/items/', {
        method: 'POST',
        body: JSON.stringify({ product_id: productId, quantity: 1, size: selectedSize(add), color: selectedColor(add) })
      }).then(function (cart) {
        renderCart(cart);
        notify('Producto agregado al carrito.');
      }).catch(function (error) { notify(error.message, true); });
      return;
    }

    var remove = event.target.closest('[data-cart-remove]');
    if (remove) {
      event.preventDefault();
      event.stopImmediatePropagation();
      request('/api/cart/items/' + remove.dataset.cartRemove + '/', { method: 'DELETE' })
        .then(renderCart).catch(function (error) { notify(error.message, true); });
      return;
    }

    var clear = event.target.closest('.clear-cart');
    if (clear) {
      event.preventDefault();
      event.stopImmediatePropagation();
      var itemIds = Array.from(new Set(Array.from(document.querySelectorAll('[data-cart-remove]')).map(function (link) {
        return link.dataset.cartRemove;
      })));
      Promise.all(itemIds.map(function (itemId) {
        return request('/api/cart/items/' + itemId + '/', { method: 'DELETE' });
      })).then(function () { return request('/api/cart/'); }).then(renderCart);
    }
  }, true);

  document.addEventListener('click', function (event) {
    var variantOption = event.target.closest('.product-size .size-list li, .product-color .color-list li');
    if (!variantOption) return;
    window.setTimeout(function () {
      var detail = variantOption.closest('.product-single-item');
      reconcileVariantSelection(detail, variantOption);
      updateVariantAvailability(detail);
    }, 0);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    var variantOption = event.target.closest('.product-size .size-list li, .product-color .color-list li');
    if (!variantOption || variantOption.getAttribute('aria-disabled') === 'true') return;
    window.setTimeout(function () {
      var detail = variantOption.closest('.product-single-item');
      reconcileVariantSelection(detail, variantOption);
      updateVariantAvailability(detail);
    }, 0);
  });

  var productDetail = document.querySelector('.product-single-item');
  reconcileVariantSelection(productDetail);
  updateVariantAvailability(productDetail);

  document.addEventListener('change', function (event) {
    var quantity = event.target.closest('[data-cart-quantity]');
    if (!quantity) return;
    request('/api/cart/items/' + quantity.dataset.cartQuantity + '/', {
      method: 'PATCH',
      body: JSON.stringify({ quantity: Math.max(1, Number(quantity.value) || 1) })
    }).then(renderCart).catch(function (error) { notify(error.message, true); });
  });

  var shippingForm = document.querySelector('[data-auto-shipping-form]');
  if (shippingForm) {
    var shippingTimer;
    var shippingStatus = shippingForm.querySelector('[data-auto-shipping-status]');
    var shippingMethod = shippingForm.querySelector('[name="delivery_method"]');
    var shippingDepartment = shippingForm.querySelector('[name="department"]');
    var shippingCity = shippingForm.querySelector('[name="city"]');

    function shippingReady() {
      return Boolean(shippingMethod && shippingMethod.value === 'pickup') ||
        Boolean(shippingDepartment && shippingDepartment.value && shippingCity && shippingCity.value.trim().length >= 2);
    }

    function scheduleShippingQuote() {
      window.clearTimeout(shippingTimer);
      if (!shippingReady()) {
        if (shippingStatus) shippingStatus.innerHTML = '<i class="fa fa-bolt" aria-hidden="true"></i> Completa departamento y ciudad; calcularemos el envío automáticamente.';
        return;
      }
      if (shippingStatus) {
        shippingStatus.classList.add('is-calculating');
        shippingStatus.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Calculando la mejor opción de envío…';
      }
      shippingTimer = window.setTimeout(function () {
        if (shippingForm.requestSubmit) shippingForm.requestSubmit();
        else shippingForm.submit();
      }, 900);
    }

    shippingForm.addEventListener('input', function (event) {
      if (event.target.matches('[name="city"], [name="postal_code"]')) scheduleShippingQuote();
    });
    shippingForm.addEventListener('change', function (event) {
      if (event.target.matches('[name="delivery_method"], [name="department"]')) scheduleShippingQuote();
    });
    document.addEventListener('cart:weight-updated', scheduleShippingQuote);
  }

  request('/api/favorites/').then(function (favorites) {
    var favoriteIds = favorites.items.map(function (item) { return item.product_id; });
    document.querySelectorAll('.btn-product-wishlist, .product-wishlist-compare a[href="shop-wishlist.html"]').forEach(function (trigger) {
      if (favoriteIds.indexOf(productIdFrom(trigger)) !== -1) trigger.classList.add('is-favorite');
    });
  }).catch(function () {});

  request('/api/cart/').then(renderCart).catch(function () {});
}());
