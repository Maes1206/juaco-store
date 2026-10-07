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

  function openShareWindow(url, name) {
    var width = 680;
    var height = 560;
    var left = Math.max(0, (window.screen.width - width) / 2);
    var top = Math.max(0, (window.screen.height - height) / 2);
    window.open(
      url,
      name,
      'noopener,noreferrer,width=' + width + ',height=' + height + ',left=' + left + ',top=' + top
    );
  }

  function shareToNetwork(network, details) {
    var text = 'Mira este producto: ' + details.title;

    if (network === 'facebook') {
      openShareWindow(
        'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(details.url),
        'facebook-share'
      );
      return;
    }

    if (network === 'whatsapp') {
      window.open(
        'https://wa.me/?text=' + encodeURIComponent(text + ' ' + details.url),
        '_blank',
        'noopener,noreferrer'
      );
      return;
    }

    if (network === 'instagram') {
      var payload = { title: details.title, text: text, url: details.url };
      if (navigator.share) {
        navigator.share(payload).catch(function (error) {
          if (error && error.name !== 'AbortError') {
            feedback('No fue posible abrir las opciones para compartir en Instagram.');
          }
        });
        return;
      }

      copyLink(details.url).then(function () {
        feedback('Enlace copiado. Pégalo en Instagram.');
        window.open('https://www.instagram.com/', '_blank', 'noopener,noreferrer');
      }).catch(function () {
        feedback('No fue posible copiar el enlace para Instagram.');
      });
    }
  }

  document.addEventListener('click', function (event) {
    var networkTrigger = event.target.closest('[data-product-share-network]');
    if (networkTrigger) {
      event.preventDefault();
      var networkDetails = shareDetails(networkTrigger);
      if (!networkDetails) return;
      shareToNetwork(networkTrigger.getAttribute('data-product-share-network'), networkDetails);
      return;
    }

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
