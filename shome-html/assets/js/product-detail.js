(function () {
  'use strict';

  var catalog = window.JuacoCatalog;
  if (!catalog) return;
  var productId = new URLSearchParams(window.location.search).get('producto');
  var product = catalog.products.find(function (item) { return item.id === productId; });
  if (!product) return;

  var brand = catalog.collections[product.brand];
  document.title = product.name + ' | Juaco Store';

  function setMeta(attribute, key, value) {
    var selector = 'meta[' + attribute + '="' + key + '"]';
    var meta = document.head.querySelector(selector);
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute(attribute, key);
      document.head.appendChild(meta);
    }
    meta.setAttribute('content', value);
  }

  var productUrl = new URL('single-product.html?producto=' + encodeURIComponent(product.id), window.location.href).href;
  var productImage = new URL(product.image, window.location.href).href;
  setMeta('name', 'description', product.description);
  setMeta('property', 'og:type', 'product');
  setMeta('property', 'og:title', product.name + ' | Juaco Store');
  setMeta('property', 'og:description', product.description);
  setMeta('property', 'og:image', productImage);
  setMeta('property', 'og:image:alt', product.name);
  setMeta('property', 'og:url', productUrl);
  setMeta('name', 'twitter:card', 'summary_large_image');
  setMeta('name', 'twitter:title', product.name + ' | Juaco Store');
  setMeta('name', 'twitter:description', product.description);
  setMeta('name', 'twitter:image', productImage);

  var canonical = document.head.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.setAttribute('rel', 'canonical');
    document.head.appendChild(canonical);
  }
  canonical.setAttribute('href', productUrl);

  document.querySelector('.product-single-info .main-title').textContent = product.name;
  document.querySelector('.product-single-info .price').textContent = product.price + ' COP';
  document.querySelector('.product-single-info > p').textContent = product.description;
  document.querySelector('.product-information p').textContent = product.description;
  document.querySelector('.product-description p').textContent = 'Tallas disponibles: ' + product.sizes.join(', ') + '. Te recomendamos elegir tu talla habitual.';
  document.querySelector('.product-info-footer .code').innerHTML = '<span>Referencia:</span> ' + product.id.toUpperCase();

  var breadcrumb = document.querySelector('.breadcrumb li:last-child');
  if (breadcrumb) breadcrumb.textContent = product.name;

  var sizes = document.querySelector('.product-size .size-list');
  sizes.innerHTML = product.sizes.map(function (size, index) {
    return '<li' + (index === 0 ? ' class="active"' : '') + '>' + size + '</li>';
  }).join('');

  var gallerySlide = '<div class="swiper-slide"><a class="lightbox-image" data-fancybox="gallery" href="' + product.image + '"><img src="' + product.image + '" width="541" height="540" alt="' + product.name + '"></a></div>';
  var navSlide = '<div class="swiper-slide"><img src="' + product.image + '" width="127" height="127" alt="' + product.name + '"></div>';
  document.querySelector('.single-product-thumb .swiper-wrapper').innerHTML = gallerySlide;
  document.querySelector('.single-product-nav .swiper-wrapper').innerHTML = navSlide;

  var header = document.querySelector('.product-page-header');
  if (header) {
    header.style.backgroundImage = 'url("' + brand.banner + '")';
    header.style.backgroundPosition = 'center';
    header.style.backgroundSize = 'cover';
  }
}());
