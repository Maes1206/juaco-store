(function () {
  'use strict';

  var catalog = window.JuacoCatalog;
  if (!catalog) return;

  function navigateToCatalog(params) {
    window.location.href = 'shop.html?' + params.toString() + '#catalog-products';
  }

  var brand = new URLSearchParams(window.location.search).get('marca') || 'jordan';
  var collection = catalog.collections[brand] || catalog.collections.jordan;
  if (!catalog.collections[brand]) brand = 'jordan';
  var products = catalog.products.filter(function (product) { return product.brand === brand; });

  document.title = collection.label + ' | Juaco Store';
  document.getElementById('catalog-title').textContent = collection.label;
  document.getElementById('catalog-breadcrumb').textContent = collection.label;
  document.getElementById('catalog-count').textContent = products.length + ' productos encontrados';

  var pageHeader = document.getElementById('catalog-page-header');
  pageHeader.style.backgroundImage = 'url("' + collection.banner + '")';
  pageHeader.style.backgroundPosition = 'center';
  pageHeader.style.backgroundRepeat = 'no-repeat';
  pageHeader.style.backgroundSize = 'cover';

  var selectedSize = new URLSearchParams(window.location.search).get('talla');
  document.querySelectorAll('.size-filter').forEach(function (button) {
    if (button.dataset.size === selectedSize) button.classList.add('active');
    button.addEventListener('click', function () {
      var params = new URLSearchParams(window.location.search);
      if (button.dataset.size === selectedSize) params.delete('talla');
      else params.set('talla', button.dataset.size);
      params.delete('pagina');
      navigateToCatalog(params);
    });
  });

  if (selectedSize) products = products.filter(function (product) { return product.sizes.indexOf(selectedSize) !== -1; });

  function priceInCop(product) {
    return Number(product.price.replace(/[^0-9]/g, ''));
  }

  function formatCop(value) {
    return '$' + value.toLocaleString('es-CO');
  }

  var rangeProducts = products.slice();
  var catalogMinPrice = rangeProducts.length ? Math.min.apply(null, rangeProducts.map(priceInCop)) : 0;
  var catalogMaxPrice = rangeProducts.length ? Math.max.apply(null, rangeProducts.map(priceInCop)) : 0;
  var query = new URLSearchParams(window.location.search);
  var allowedSorts = ['default', 'price-asc', 'price-desc', 'name-asc'];
  var selectedSort = query.get('orden') || 'default';
  if (allowedSorts.indexOf(selectedSort) === -1) selectedSort = 'default';
  var productSort = document.getElementById('product-sort');
  productSort.value = selectedSort;
  productSort.addEventListener('change', function () {
    var params = new URLSearchParams(window.location.search);
    if (productSort.value === 'default') params.delete('orden');
    else params.set('orden', productSort.value);
    params.delete('pagina');
    navigateToCatalog(params);
  });
  var selectedMinPrice = Number(query.get('precioMin')) || catalogMinPrice;
  var selectedMaxPrice = Number(query.get('precioMax')) || catalogMaxPrice;
  selectedMinPrice = Math.max(catalogMinPrice, Math.min(selectedMinPrice, catalogMaxPrice));
  selectedMaxPrice = Math.max(selectedMinPrice, Math.min(selectedMaxPrice, catalogMaxPrice));

  var minLabel = document.getElementById('price-min-label');
  var maxLabel = document.getElementById('price-max-label');
  function updatePriceLabels(values) {
    minLabel.textContent = 'Desde ' + formatCop(values[0]);
    maxLabel.textContent = 'Hasta ' + formatCop(values[1]);
  }
  updatePriceLabels([selectedMinPrice, selectedMaxPrice]);

  if (window.jQuery && window.jQuery.fn.slider && catalogMinPrice !== catalogMaxPrice) {
    var priceRange = window.jQuery('#price-range');
    priceRange.slider({
      range: true,
      min: catalogMinPrice,
      max: catalogMaxPrice,
      step: 1000,
      values: [selectedMinPrice, selectedMaxPrice],
      slide: function (event, ui) {
        updatePriceLabels(ui.values);
      },
      stop: function (event, ui) {
        var params = new URLSearchParams(window.location.search);
        params.set('precioMin', ui.values[0]);
        params.set('precioMax', ui.values[1]);
        params.delete('pagina');
        navigateToCatalog(params);
      }
    });
  }

  products = products.filter(function (product) {
    var price = priceInCop(product);
    return price >= selectedMinPrice && price <= selectedMaxPrice;
  });

  var colorAnalyzer = window.JuacoColorAnalyzer;
  var selectedColor = query.get('color');
  var colorFilter = document.getElementById('catalog-color-filter');
  var clearColorFilter = document.getElementById('clear-color-filter');
  clearColorFilter.disabled = !selectedColor;
  clearColorFilter.addEventListener('click', function () {
    var params = new URLSearchParams(window.location.search);
    params.delete('color');
    params.delete('pagina');
    navigateToCatalog(params);
  });
  colorAnalyzer.palette.forEach(function (color) {
    var circle = document.createElement('li');
    circle.dataset.color = color.id;
    circle.style.backgroundColor = color.hex;
    circle.setAttribute('role', 'button');
    circle.setAttribute('tabindex', '0');
    circle.setAttribute('aria-label', 'Filtrar por ' + color.label);
    circle.title = color.label;
    if (color.id === selectedColor) circle.classList.add('active');

    function selectColor() {
      var params = new URLSearchParams(window.location.search);
      if (selectedColor === color.id) params.delete('color');
      else params.set('color', color.id);
      params.delete('pagina');
      navigateToCatalog(params);
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

  function productCard(product) {
    var detailUrl = 'single-product.html?producto=' + product.id;
    var colorData = product.colorAnalysis ? ' data-dominant-color="' + product.colorAnalysis.category + '" data-color-percentage="' + product.colorAnalysis.percentage + '" data-product-colors="' + product.colorAnalysis.colors.map(function (color) { return color.category; }).join(',') + '"' : '';
    return '<div class="col-sm-6 col-lg-4 catalog-product" data-brand="' + brand + '"' + colorData + '><div class="product-item"><div class="inner-content">' +
      '<div class="product-thumb"><a href="' + detailUrl + '"><img src="' + product.image + '" width="270" height="274" alt="' + product.name + '"></a>' +
      '<div class="product-action"><a class="btn-product-wishlist" href="shop-wishlist.html"><i class="fa fa-heart"></i></a><a class="btn-product-cart" href="shop-cart.html"><i class="fa fa-shopping-cart"></i></a></div></div>' +
      '<div class="product-info"><div class="category"><ul><li><a href="shop.html?marca=' + brand + '">' + collection.label + '</a></li></ul></div>' +
      '<h4 class="title"><a href="' + detailUrl + '">' + product.name + '</a></h4><div class="prices"><span class="price">' + product.price + '</span></div></div>' +
      '</div></div></div>';
  }

  function renderCatalog(filteredProducts) {
    products = filteredProducts.slice();
    if (selectedSort === 'price-asc') products.sort(function (a, b) { return priceInCop(a) - priceInCop(b); });
    if (selectedSort === 'price-desc') products.sort(function (a, b) { return priceInCop(b) - priceInCop(a); });
    if (selectedSort === 'name-asc') products.sort(function (a, b) { return a.name.localeCompare(b.name, 'es'); });
    document.getElementById('catalog-count').textContent = products.length + ' productos encontrados';
    var activeBrandFilter = document.getElementById('active-brand-filter');
    var brandParams = new URLSearchParams(window.location.search);
    brandParams.set('marca', brand);
    brandParams.delete('pagina');
    activeBrandFilter.href = 'shop.html?' + brandParams.toString() + '#catalog-products';
    activeBrandFilter.innerHTML = collection.label + ' <span>(' + products.length + ')</span>';

    var productsPerPage = 6;
    var totalPages = Math.max(1, Math.ceil(products.length / productsPerPage));
    var selectedPage = parseInt(new URLSearchParams(window.location.search).get('pagina'), 10) || 1;
    selectedPage = Math.min(Math.max(selectedPage, 1), totalPages);

    function pagination() {
      if (totalPages < 2) return '';
      var links = '';
      for (var page = 1; page <= totalPages; page += 1) {
        var active = page === selectedPage ? ' class="active" aria-current="page"' : '';
        var pageParams = new URLSearchParams(window.location.search);
        pageParams.set('marca', brand);
        pageParams.set('pagina', page);
        links += '<li><a' + active + ' href="shop.html?' + pageParams.toString() + '#catalog-products">' + page + '</a></li>';
      }
      return '<div class="col-12"><div class="pagination-items"><ul class="pagination justify-content-end mb--0">' + links + '</ul></div></div>';
    }

    function renderPage(container) {
      if (!container) return;
      var firstProduct = (selectedPage - 1) * productsPerPage;
      var cards = products.slice(firstProduct, firstProduct + productsPerPage).map(productCard).join('');
      if (!cards) cards = '<div class="col-12"><p class="catalog-empty-message">No encontramos productos cuyo color dominante coincida con este filtro.</p></div>';
      container.innerHTML = cards + pagination();
    }

    renderPage(document.querySelector('#nav-grid > .row'));
    renderPage(document.querySelector('#nav-list > .row'));
  }

  if (selectedColor) {
    document.getElementById('catalog-count').textContent = 'Analizando colores…';
    colorAnalyzer.analyzeProducts(products).then(function (analyzedProducts) {
      renderCatalog(analyzedProducts.filter(function (product) {
        return product.colorAnalysis && product.colorAnalysis.colors.some(function (color) {
          return color.category === selectedColor;
        });
      }));
    });
  } else {
    renderCatalog(products);
  }
}());
