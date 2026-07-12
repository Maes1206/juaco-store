(function () {
  'use strict';

  var catalog = window.JuacoCatalog;
  var colorAnalyzer = window.JuacoColorAnalyzer;
  if (!catalog || !colorAnalyzer) return;

  var brand = new URLSearchParams(window.location.search).get('marca') || 'jordan';
  var collection = catalog.collections[brand] || catalog.collections.jordan;
  if (!catalog.collections[brand]) brand = 'jordan';
  var catalogProducts = catalog.products.filter(function (product) { return product.brand === brand; });
  var allowedSorts = ['default', 'price-asc', 'price-desc', 'name-asc'];
  var productsPerPage = 6;
  var filterRequest = 0;
  var priceRange;

  function priceInCop(product) {
    return Number(product.price.replace(/[^0-9]/g, ''));
  }

  function formatCop(value) {
    return '$' + value.toLocaleString('es-CO');
  }

  var catalogMinPrice = Math.min.apply(null, catalogProducts.map(priceInCop));
  var catalogMaxPrice = Math.max.apply(null, catalogProducts.map(priceInCop));

  function readState() {
    var params = new URLSearchParams(window.location.search);
    var sort = params.get('orden') || 'default';
    var minPrice = Number(params.get('precioMin')) || catalogMinPrice;
    var maxPrice = Number(params.get('precioMax')) || catalogMaxPrice;
    minPrice = Math.max(catalogMinPrice, Math.min(minPrice, catalogMaxPrice));
    maxPrice = Math.max(minPrice, Math.min(maxPrice, catalogMaxPrice));
    return {
      size: params.get('talla'),
      color: params.get('color'),
      minPrice: minPrice,
      maxPrice: maxPrice,
      sort: allowedSorts.indexOf(sort) === -1 ? 'default' : sort,
      page: Math.max(1, parseInt(params.get('pagina'), 10) || 1)
    };
  }

  var state = readState();
  var catalogResults = document.getElementById('nav-tabContent');
  var catalogCount = document.getElementById('catalog-count');
  var activeBrandFilter = document.getElementById('active-brand-filter');
  var minLabel = document.getElementById('price-min-label');
  var maxLabel = document.getElementById('price-max-label');
  var productSort = document.getElementById('product-sort');
  var colorFilter = document.getElementById('catalog-color-filter');
  var clearColorFilter = document.getElementById('clear-color-filter');

  document.title = collection.label + ' | Juaco Store';
  document.getElementById('catalog-title').textContent = collection.label;
  document.getElementById('catalog-breadcrumb').textContent = collection.label;

  var pageHeader = document.getElementById('catalog-page-header');
  // El catálogo usa banners propios por marca. Se desactiva el parallax
  // genérico de la cabecera para que no sobrescriba esta imagen estática.
  pageHeader.classList.remove('has-parallax-background');
  pageHeader.style.removeProperty('--page-parallax-image');
  pageHeader.style.removeProperty('--page-parallax-position');
  pageHeader.style.removeProperty('--page-parallax-offset');
  pageHeader.style.backgroundImage = 'url("' + collection.banner + '")';
  pageHeader.style.backgroundPosition = 'center center';
  pageHeader.style.backgroundRepeat = 'no-repeat';
  pageHeader.style.backgroundSize = 'cover';

  function updatePriceLabels() {
    minLabel.textContent = 'Desde ' + formatCop(state.minPrice);
    maxLabel.textContent = 'Hasta ' + formatCop(state.maxPrice);
  }

  function updateUrl() {
    var params = new URLSearchParams();
    params.set('marca', brand);
    if (state.size) params.set('talla', state.size);
    if (state.color) params.set('color', state.color);
    if (state.minPrice !== catalogMinPrice) params.set('precioMin', state.minPrice);
    if (state.maxPrice !== catalogMaxPrice) params.set('precioMax', state.maxPrice);
    if (state.sort !== 'default') params.set('orden', state.sort);
    if (state.page > 1) params.set('pagina', state.page);
    window.history.pushState({}, '', window.location.pathname + '?' + params.toString() + '#catalog-products');
  }

  function animateResults(shouldScroll) {
    catalogResults.classList.remove('is-filtering');
    window.requestAnimationFrame(function () {
      catalogResults.classList.add('is-filtering');
    });
    window.setTimeout(function () {
      catalogResults.classList.remove('is-filtering');
    }, 520);
    if (shouldScroll) {
      window.setTimeout(function () {
        catalogResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 40);
    }
  }

  function refreshControls() {
    document.querySelectorAll('.size-filter').forEach(function (button) {
      button.classList.toggle('active', button.dataset.size === state.size);
    });
    document.querySelectorAll('#catalog-color-filter > li').forEach(function (circle) {
      circle.classList.toggle('active', circle.dataset.color === state.color);
    });
    clearColorFilter.disabled = !state.color;
    productSort.value = state.sort;
    updatePriceLabels();
    if (priceRange) priceRange.slider('values', [state.minPrice, state.maxPrice]);
  }

  function productCard(product, index) {
    var detailUrl = 'single-product.html?producto=' + product.id;
    var colorData = product.colorAnalysis ? ' data-dominant-color="' + product.colorAnalysis.category + '" data-color-percentage="' + product.colorAnalysis.percentage + '" data-product-colors="' + product.colorAnalysis.colors.map(function (color) { return color.category; }).join(',') + '"' : '';
    return '<div class="col-sm-6 col-lg-4 catalog-product" style="--card-delay:' + (index * 55) + 'ms" data-brand="' + brand + '"' + colorData + '><div class="product-item"><div class="inner-content">' +
      '<div class="product-thumb"><a href="' + detailUrl + '"><img src="' + product.image + '" width="270" height="274" alt="' + product.name + '"></a>' +
      '<div class="product-action"><a class="btn-product-wishlist" href="shop-wishlist.html"><i class="fa fa-heart"></i></a><a class="btn-product-cart" href="shop-cart.html"><i class="fa fa-shopping-cart"></i></a><button class="btn-product-share" type="button" data-product-share aria-label="Compartir producto" title="Compartir producto"><i class="fa fa-share-alt"></i></button></div></div>' +
      '<div class="product-info"><div class="category"><ul><li><a href="shop.html?marca=' + brand + '">' + collection.label + '</a></li></ul></div>' +
      '<h4 class="title"><a href="' + detailUrl + '">' + product.name + '</a></h4><div class="prices"><span class="price">' + product.price + '</span></div></div>' +
      '</div></div></div>';
  }

  function renderCatalog(filteredProducts) {
    var products = filteredProducts.slice();
    if (state.sort === 'price-asc') products.sort(function (a, b) { return priceInCop(a) - priceInCop(b); });
    if (state.sort === 'price-desc') products.sort(function (a, b) { return priceInCop(b) - priceInCop(a); });
    if (state.sort === 'name-asc') products.sort(function (a, b) { return a.name.localeCompare(b.name, 'es'); });

    var totalPages = Math.max(1, Math.ceil(products.length / productsPerPage));
    state.page = Math.min(state.page, totalPages);
    catalogCount.textContent = products.length + ' productos encontrados';
    activeBrandFilter.href = 'shop.html?marca=' + brand + '#catalog-products';
    activeBrandFilter.innerHTML = collection.label + ' <span>(' + products.length + ')</span>';

    function pagination() {
      if (totalPages < 2) return '';
      var links = '';
      for (var page = 1; page <= totalPages; page += 1) {
        var active = page === state.page ? ' class="active" aria-current="page"' : '';
        links += '<li><a' + active + ' class="catalog-page-link" data-page="' + page + '" href="#catalog-products">' + page + '</a></li>';
      }
      return '<div class="col-12"><div class="pagination-items"><ul class="pagination justify-content-end mb--0">' + links + '</ul></div></div>';
    }

    function renderPage(container) {
      if (!container) return;
      var firstProduct = (state.page - 1) * productsPerPage;
      var pageProducts = products.slice(firstProduct, firstProduct + productsPerPage);
      var cards = pageProducts.map(productCard).join('');
      if (!cards) cards = '<div class="col-12"><p class="catalog-empty-message">No encontramos productos que coincidan con estos filtros.</p></div>';
      container.innerHTML = cards + pagination();
    }

    renderPage(document.querySelector('#nav-grid > .row'));
    renderPage(document.querySelector('#nav-list > .row'));
  }

  function applyFilters(options) {
    var settings = options || {};
    var requestId = ++filterRequest;
    var filteredProducts = catalogProducts.filter(function (product) {
      var matchesSize = !state.size || product.sizes.indexOf(state.size) !== -1;
      var productPrice = priceInCop(product);
      var matchesPrice = productPrice >= state.minPrice && productPrice <= state.maxPrice;
      return matchesSize && matchesPrice;
    });

    function finish(products) {
      if (requestId !== filterRequest) return;
      renderCatalog(products);
      refreshControls();
      if (settings.updateUrl) updateUrl();
      if (settings.animate) animateResults(settings.scroll);
    }

    if (state.color) {
      catalogCount.textContent = 'Analizando colores…';
      colorAnalyzer.analyzeProducts(filteredProducts).then(function (analyzedProducts) {
        finish(analyzedProducts.filter(function (product) {
          return product.colorAnalysis && product.colorAnalysis.colors.some(function (color) {
            return color.category === state.color;
          });
        }));
      });
    } else {
      finish(filteredProducts);
    }
  }

  document.querySelectorAll('.size-filter').forEach(function (button) {
    button.addEventListener('click', function () {
      state.size = state.size === button.dataset.size ? null : button.dataset.size;
      state.page = 1;
      applyFilters({ updateUrl: true, animate: true, scroll: true });
    });
  });

  productSort.addEventListener('change', function () {
    state.sort = productSort.value;
    state.page = 1;
    applyFilters({ updateUrl: true, animate: true, scroll: false });
  });

  clearColorFilter.addEventListener('click', function () {
    state.color = null;
    state.page = 1;
    applyFilters({ updateUrl: true, animate: true, scroll: true });
  });

  colorAnalyzer.palette.forEach(function (color) {
    var circle = document.createElement('li');
    circle.dataset.color = color.id;
    circle.style.backgroundColor = color.hex;
    circle.setAttribute('role', 'button');
    circle.setAttribute('tabindex', '0');
    circle.setAttribute('aria-label', 'Filtrar por ' + color.label);
    circle.title = color.label;
    function selectColor() {
      state.color = state.color === color.id ? null : color.id;
      state.page = 1;
      applyFilters({ updateUrl: true, animate: true, scroll: true });
    }
    circle.addEventListener('click', selectColor);
    circle.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectColor();
      }
    });
    colorFilter.appendChild(circle);
  });

  if (window.jQuery && window.jQuery.fn.slider && catalogMinPrice !== catalogMaxPrice) {
    priceRange = window.jQuery('#price-range');
    priceRange.slider({
      range: true,
      min: catalogMinPrice,
      max: catalogMaxPrice,
      step: 1000,
      values: [state.minPrice, state.maxPrice],
      slide: function (event, ui) {
        minLabel.textContent = 'Desde ' + formatCop(ui.values[0]);
        maxLabel.textContent = 'Hasta ' + formatCop(ui.values[1]);
      },
      stop: function (event, ui) {
        state.minPrice = ui.values[0];
        state.maxPrice = ui.values[1];
        state.page = 1;
        applyFilters({ updateUrl: true, animate: true, scroll: true });
      }
    });
  }

  document.getElementById('nav-tabContent').addEventListener('click', function (event) {
    var pageLink = event.target.closest('.catalog-page-link');
    if (!pageLink) return;
    event.preventDefault();
    state.page = Number(pageLink.dataset.page);
    applyFilters({ updateUrl: true, animate: true, scroll: true });
  });

  window.addEventListener('popstate', function () {
    state = readState();
    applyFilters({ animate: true, scroll: false });
  });

  applyFilters();
  colorAnalyzer.analyzeProducts(catalogProducts);
}());
