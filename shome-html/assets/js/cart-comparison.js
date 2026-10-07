(function () {
  'use strict';

  var root = document.querySelector('[data-cart-comparison]');
  if (!root) return;

  var empty = root.querySelector('[data-comparison-empty]');
  var tool = root.querySelector('[data-comparison-tool]');
  var openButton = root.querySelector('[data-comparison-open]');
  var modal = root.querySelector('[data-comparison-modal]');
  var selectA = root.querySelector('[data-comparison-select="a"]');
  var selectB = root.querySelector('[data-comparison-select="b"]');
  var result = root.querySelector('[data-comparison-result]');
  var products = [];
  var selectedA = '';
  var selectedB = '';

  function openComparison() {
    modal.hidden = false;
    openButton.setAttribute('aria-expanded', 'true');
    document.body.classList.add('comparison-modal-open');
    window.requestAnimationFrame(function () {
      modal.classList.add('is-visible');
      var closeButton = modal.querySelector('.cart-comparison-modal__close');
      if (closeButton) closeButton.focus();
    });
  }

  function closeComparison() {
    modal.classList.remove('is-visible');
    modal.hidden = true;
    openButton.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('comparison-modal-open');
    openButton.focus();
  }

  function escapeHtml(value) {
    var node = document.createElement('div');
    node.textContent = String(value == null ? '' : value);
    return node.innerHTML;
  }

  function money(value) {
    return '$' + Number(value || 0).toLocaleString('es-CO') + ' COP';
  }

  function unique(values) {
    return values.filter(function (value, index, list) {
      return value && list.indexOf(value) === index;
    });
  }

  function comparisonProducts(items) {
    var byProduct = {};
    (items || []).forEach(function (item) {
      if (!byProduct[item.product_id]) {
        byProduct[item.product_id] = Object.assign({}, item, {
          cart_quantity: 0,
          cart_sizes: [],
          cart_colors: []
        });
      }
      byProduct[item.product_id].cart_quantity += Number(item.quantity || 0);
      if (item.size) byProduct[item.product_id].cart_sizes.push(item.size);
      if (item.color) byProduct[item.product_id].cart_colors.push(item.color);
    });
    return Object.keys(byProduct).map(function (id) {
      byProduct[id].cart_sizes = unique(byProduct[id].cart_sizes);
      byProduct[id].cart_colors = unique(byProduct[id].cart_colors);
      return byProduct[id];
    });
  }

  function optionMarkup(product) {
    return '<option value="' + escapeHtml(product.product_id) + '">' + escapeHtml(product.name) + '</option>';
  }

  function productCard(product) {
    return '<article class="comparison-product-card">' +
      '<a href="single-product.html?producto=' + encodeURIComponent(product.product_id) + '">' +
        '<img src="' + escapeHtml(product.image) + '" width="90" height="90" alt="' + escapeHtml(product.name) + '">' +
      '</a>' +
      '<span>' + escapeHtml(product.brand) + '</span>' +
      '<h6><a href="single-product.html?producto=' + encodeURIComponent(product.product_id) + '">' + escapeHtml(product.name) + '</a></h6>' +
    '</article>';
  }

  function metric(label, left, right, leftBest, rightBest) {
    return '<div class="comparison-metric"><span class="comparison-metric__label">' + escapeHtml(label) + '</span>' +
      '<div><span' + (leftBest ? ' class="is-best"' : '') + '>' + escapeHtml(left) + '</span>' +
      '<span' + (rightBest ? ' class="is-best"' : '') + '>' + escapeHtml(right) + '</span></div></div>';
  }

  function listOrFallback(values, fallback) {
    return values && values.length ? values.join(', ') : fallback;
  }

  function hasReviews(product) {
    return Number(product.review_count || 0) > 0;
  }

  function reviewLabel(product) {
    if (!hasReviews(product)) return 'Aún sin reseñas';
    var count = Number(product.review_count);
    var average = Number(product.review_average).toLocaleString('es-CO', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    });
    return average + '/5 · ' + count + (count === 1 ? ' reseña' : ' reseñas');
  }

  function recommendationLabel(product) {
    if (!hasReviews(product)) return 'Aún sin datos';
    return Number(product.recommendation_percent || 0) + '% lo recomienda';
  }

  function renderResult() {
    var left = products.find(function (product) { return product.product_id === selectedA; });
    var right = products.find(function (product) { return product.product_id === selectedB; });
    if (!left || !right) return;

    var leftPriceBest = Number(left.price) < Number(right.price);
    var rightPriceBest = Number(right.price) < Number(left.price);
    var leftStockBest = Number(left.stock) > Number(right.stock);
    var rightStockBest = Number(right.stock) > Number(left.stock);
    var leftWeightBest = Number(left.weight_kg) < Number(right.weight_kg);
    var rightWeightBest = Number(right.weight_kg) < Number(left.weight_kg);
    var bothHaveReviews = hasReviews(left) && hasReviews(right);
    var leftRatingBest = bothHaveReviews && Number(left.review_average) > Number(right.review_average);
    var rightRatingBest = bothHaveReviews && Number(right.review_average) > Number(left.review_average);
    var leftRecommendationBest = bothHaveReviews && Number(left.recommendation_percent) > Number(right.recommendation_percent);
    var rightRecommendationBest = bothHaveReviews && Number(right.recommendation_percent) > Number(left.recommendation_percent);

    result.innerHTML = '<div class="comparison-products">' + productCard(left) + productCard(right) + '</div>' +
      metric('Precio', money(left.price), money(right.price), leftPriceBest, rightPriceBest) +
      metric('Marca', left.brand, right.brand, false, false) +
      metric('Año de lanzamiento', left.release_year || 'Por confirmar', right.release_year || 'Por confirmar', false, false) +
      metric('Valoración de clientes', reviewLabel(left), reviewLabel(right), leftRatingBest, rightRatingBest) +
      metric('Recomendación', recommendationLabel(left), recommendationLabel(right), leftRecommendationBest, rightRecommendationBest) +
      metric('Disponibilidad', left.stock + ' unidades', right.stock + ' unidades', leftStockBest, rightStockBest) +
      metric('Peso por par', Number(left.weight_kg).toLocaleString('es-CO') + ' kg', Number(right.weight_kg).toLocaleString('es-CO') + ' kg', leftWeightBest, rightWeightBest) +
      metric('Tallas disponibles', listOrFallback(left.sizes, 'Por confirmar'), listOrFallback(right.sizes, 'Por confirmar'), false, false) +
      metric('En tu carrito', left.cart_quantity + ' · Talla ' + listOrFallback(left.cart_sizes, '—'), right.cart_quantity + ' · Talla ' + listOrFallback(right.cart_sizes, '—'), false, false) +
      '<div class="comparison-actions"><a href="single-product.html?producto=' + encodeURIComponent(left.product_id) + '">Ver ' + escapeHtml(left.brand) + '</a>' +
      '<a href="single-product.html?producto=' + encodeURIComponent(right.product_id) + '">Ver ' + escapeHtml(right.brand) + '</a></div>';
  }

  function normalizeSelections() {
    var ids = products.map(function (product) { return product.product_id; });
    if (ids.indexOf(selectedA) === -1) selectedA = ids[0] || '';
    if (ids.indexOf(selectedB) === -1 || selectedB === selectedA) {
      selectedB = ids.find(function (id) { return id !== selectedA; }) || '';
    }
  }

  function render(cart) {
    products = comparisonProducts(cart && cart.items);
    var enabled = products.length >= 2;
    empty.hidden = enabled;
    tool.hidden = !enabled;

    if (!enabled) {
      var title = empty.querySelector('strong');
      var copy = empty.querySelector('span');
      if (title) title.textContent = products.length ? 'Agrega un producto diferente' : 'Tu carrito aún no tiene productos';
      if (copy) copy.textContent = products.length ? 'Necesitas otro modelo para activar la comparación.' : 'Explora la tienda y elige dos modelos para compararlos.';
      return;
    }

    normalizeSelections();
    var options = products.map(optionMarkup).join('');
    selectA.innerHTML = options;
    selectB.innerHTML = options;
    selectA.value = selectedA;
    selectB.value = selectedB;
    renderResult();
  }

  function selectionChanged(changedSelect) {
    if (changedSelect === selectA) selectedA = selectA.value;
    else selectedB = selectB.value;

    if (selectedA === selectedB) {
      if (changedSelect === selectA) selectedB = products.find(function (product) { return product.product_id !== selectedA; }).product_id;
      else selectedA = products.find(function (product) { return product.product_id !== selectedB; }).product_id;
    }
    selectA.value = selectedA;
    selectB.value = selectedB;
    renderResult();
  }

  selectA.addEventListener('change', function () { selectionChanged(selectA); });
  selectB.addEventListener('change', function () { selectionChanged(selectB); });
  openButton.addEventListener('click', openComparison);
  modal.querySelectorAll('[data-comparison-close]').forEach(function (button) {
    button.addEventListener('click', closeComparison);
  });
  modal.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = Array.prototype.filter.call(
      modal.querySelectorAll('button:not([disabled]):not([tabindex="-1"]), select:not([disabled]), a[href]'),
      function (element) { return element.offsetParent !== null; }
    );
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !modal.hidden) closeComparison();
  });
  document.addEventListener('cart:rendered', function (event) { render(event.detail); });
  if (window.JuacoCartState) render(window.JuacoCartState);
}());
