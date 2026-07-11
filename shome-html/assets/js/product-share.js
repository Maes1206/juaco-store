(function () {
  'use strict';

  function normalizeImagePath(path) {
    return (path || '').split('?')[0].replace(/^\.\//, '');
  }

  function productForImage(imagePath) {
    var catalog = window.JuacoCatalog;
    if (!catalog || !catalog.products) return null;
    var normalizedImage = normalizeImagePath(imagePath);
    return catalog.products.find(function (product) {
      return normalizeImagePath(product.image) === normalizedImage;
    }) || null;
  }

  function detailUrl(product) {
    return new URL('single-product.html?producto=' + encodeURIComponent(product.id), window.location.href).href;
  }

  function shareDetails(trigger) {
    var singleProduct = trigger.closest('.product-single-item');
    if (singleProduct) {
      var singleImage = singleProduct.querySelector('.single-product-thumb img');
      var singleTitle = singleProduct.querySelector('.product-single-info .main-title');
      return {
        title: singleTitle ? singleTitle.textContent.trim() : document.title,
        url: window.location.href,
        image: singleImage ? singleImage.currentSrc || singleImage.src : ''
      };
    }

    var card = trigger.closest('.product-item');
    if (!card) return null;
    var image = card.querySelector('.product-thumb img');
    var product = productForImage(image ? image.getAttribute('src') : '');
    var title = card.querySelector('.product-info .title');
    var cardLink = card.querySelector('.product-info .title a, .product-thumb > a:not(.banner-link-overlay)');

    return {
      title: product ? product.name : (title ? title.textContent.trim() : document.title),
      url: product ? detailUrl(product) : new URL(cardLink ? cardLink.getAttribute('href') : window.location.href, window.location.href).href,
      image: image ? image.currentSrc || image.src : ''
    };
  }

  function feedback(message) {
    var element = document.getElementById('product-share-feedback');
    if (!element) {
      element = document.createElement('div');
      element.id = 'product-share-feedback';
      element.className = 'product-share-feedback';
      element.setAttribute('role', 'status');
      element.setAttribute('aria-live', 'polite');
      document.body.appendChild(element);
    }
    element.textContent = message;
    element.classList.add('is-visible');
    window.clearTimeout(feedback.timeout);
    feedback.timeout = window.setTimeout(function () {
      element.classList.remove('is-visible');
    }, 2600);
  }

  function copyLink(url) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(url);
    }
    var input = document.createElement('textarea');
    input.value = url;
    input.setAttribute('readonly', '');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
    return Promise.resolve();
  }

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-product-share]');
    if (!trigger) return;
    event.preventDefault();

    var details = shareDetails(trigger);
    if (!details) return;
    var payload = {
      title: details.title,
      text: 'Mira este producto: ' + details.title,
      url: details.url
    };

    if (navigator.share) {
      navigator.share(payload).catch(function (error) {
        if (error && error.name !== 'AbortError') feedback('No fue posible abrir las opciones para compartir.');
      });
      return;
    }

    copyLink(details.url).then(function () {
      feedback('Enlace del producto copiado.');
    }).catch(function () {
      feedback('No fue posible copiar el enlace.');
    });
  });
}());
