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
      '<span class="product-price">' + item.quantity + ' × ' + money(item.price) + '</span>' +
    '</li>';
  }

  function cartRow(item) {
    return '<tr class="cart-product-item" data-cart-row="' + item.id + '">' +
      '<td class="product-remove"><a href="#" data-cart-remove="' + item.id + '" aria-label="Eliminar producto"><i class="fa fa-trash-o"></i></a></td>' +
      '<td class="product-thumb"><a href="single-product.html?producto=' + encodeURIComponent(item.product_id) + '"><img src="' + item.image + '" width="90" height="110" alt="' + item.name + '"></a></td>' +
      '<td class="product-name"><h4 class="title"><a href="single-product.html?producto=' + encodeURIComponent(item.product_id) + '">' + item.name + '</a></h4>' + (item.size ? '<small>Talla: ' + item.size + '</small>' : '') + '</td>' +
      '<td class="product-price"><span class="price">' + money(item.price) + '</span></td>' +
      '<td class="product-quantity"><div class="pro-qty"><input type="number" min="1" class="quantity" data-cart-quantity="' + item.id + '" value="' + item.quantity + '"></div></td>' +
      '<td class="product-subtotal"><span class="price">' + money(item.subtotal) + '</span></td></tr>';
  }

  function renderCart(cart) {
    updateBadges(cart);
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
    document.querySelectorAll('.cart-subtotal .price, .order-total .price, [data-cart-subtotal]').forEach(function (node) {
      node.textContent = money(cart.subtotal);
    });
    document.querySelectorAll('.aside-cart-wrapper .cart-total .amount').forEach(function (node) {
      node.textContent = money(cart.subtotal);
    });
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
      request('/api/cart/items/', {
        method: 'POST',
        body: JSON.stringify({ product_id: productId, quantity: 1, size: selectedSize(add) })
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

  document.addEventListener('change', function (event) {
    var quantity = event.target.closest('[data-cart-quantity]');
    if (!quantity) return;
    request('/api/cart/items/' + quantity.dataset.cartQuantity + '/', {
      method: 'PATCH',
      body: JSON.stringify({ quantity: Math.max(1, Number(quantity.value) || 1) })
    }).then(renderCart).catch(function (error) { notify(error.message, true); });
  });

  request('/api/favorites/').then(function (favorites) {
    var favoriteIds = favorites.items.map(function (item) { return item.product_id; });
    document.querySelectorAll('.btn-product-wishlist, .product-wishlist-compare a[href="shop-wishlist.html"]').forEach(function (trigger) {
      if (favoriteIds.indexOf(productIdFrom(trigger)) !== -1) trigger.classList.add('is-favorite');
    });
  }).catch(function () {});

  request('/api/cart/').then(renderCart).catch(function () {});
}());
