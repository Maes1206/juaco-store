(function () {
  'use strict';

  var catalog = window.JuacoCatalog;
  if (!catalog || !catalog.products) return;

  var productsByImage = {};
  catalog.products.forEach(function (product) {
    productsByImage[product.image.replace(/^\.\//, '')] = product;
  });

  document.querySelectorAll('.product-item').forEach(function (card) {
    var image = card.querySelector('.product-thumb > a > img');
    if (!image) return;

    var product = productsByImage[(image.getAttribute('src') || '').replace(/^\.\//, '')];
    if (!product) return;

    var detailUrl = 'single-product.html?producto=' + encodeURIComponent(product.id);
    card.querySelectorAll('.product-thumb > a, .product-info .title > a').forEach(function (link) {
      link.setAttribute('href', detailUrl);
    });

    image.alt = product.name;
    var title = card.querySelector('.product-info .title > a');
    if (title) title.textContent = product.name;
    var prices = card.querySelector('.product-info .prices');
    if (prices) prices.innerHTML = '<span class="price">' + product.price + '</span>';
  });
}());
