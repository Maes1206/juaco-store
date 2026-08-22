(function () {
  'use strict';

  var root = document.querySelector('.product-single-item[data-product-id]');
  if (!root) return;

  var productId = root.getAttribute('data-product-id');
  var productNameNode = root.querySelector('.product-single-info .main-title');
  var descriptionNode = root.querySelector('.product-single-info > p');
  var imageNode = root.querySelector('.single-product-thumb img');
  var productName = productNameNode ? productNameNode.textContent.trim() : document.title;
  var description = descriptionNode ? descriptionNode.textContent.trim() : '';
  var productUrl = new URL('single-product.html?producto=' + encodeURIComponent(productId), window.location.href).href;
  var productImage = imageNode ? new URL(imageNode.getAttribute('src'), window.location.href).href : '';

  function setMeta(attribute, key, value) {
    if (!value) return;
    var selector = 'meta[' + attribute + '="' + key + '"]';
    var meta = document.head.querySelector(selector);
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute(attribute, key);
      document.head.appendChild(meta);
    }
    meta.setAttribute('content', value);
  }

  setMeta('name', 'description', description);
  setMeta('property', 'og:type', 'product');
  setMeta('property', 'og:title', productName + ' | Nexus Luxury Footwear');
  setMeta('property', 'og:description', description);
  setMeta('property', 'og:image', productImage);
  setMeta('property', 'og:image:alt', productName);
  setMeta('property', 'og:url', productUrl);
  setMeta('name', 'twitter:card', 'summary_large_image');
  setMeta('name', 'twitter:title', productName + ' | Nexus Luxury Footwear');
  setMeta('name', 'twitter:description', description);
  setMeta('name', 'twitter:image', productImage);

  var canonical = document.head.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.setAttribute('rel', 'canonical');
    document.head.appendChild(canonical);
  }
  canonical.setAttribute('href', productUrl);

  function selectVariant(option) {
    var list = option.parentElement;
    Array.prototype.forEach.call(list.children, function (item) {
      var active = item === option;
      item.classList.toggle('active', active);
      item.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  root.addEventListener('click', function (event) {
    var option = event.target.closest('.color-list li, .size-list li');
    if (option && root.contains(option)) selectVariant(option);
  });

  root.addEventListener('keydown', function (event) {
    var option = event.target.closest('.color-list li, .size-list li');
    if (option && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      selectVariant(option);
    }
  });

  var catalog = window.JuacoCatalog;
  var brandKey = root.getAttribute('data-product-brand');
  var brand = catalog && catalog.collections ? catalog.collections[brandKey] : null;
  var header = document.querySelector('.product-page-header');
  if (header && brand && brand.banner) {
    header.style.backgroundImage = 'url("' + brand.banner + '")';
    header.style.backgroundPosition = 'center';
    header.style.backgroundSize = 'cover';
  }
}());