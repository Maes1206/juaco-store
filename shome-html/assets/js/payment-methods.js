/* Fuente única de los métodos mostrados en los pies de página. */
(function () {
  'use strict';
  var paymentMethods = [
    { id: 'amex', label: 'American Express', content: 'AMERICAN<br>EXPRESS' },
    { id: 'paypal', label: 'PayPal', content: 'PayPal' },
    { id: 'mastercard', label: 'Mastercard', content: '<span></span><span></span>' },
    { id: 'bold', label: 'Pago con Bold', content: '<span>Bold</span>' },
    { id: 'visa', label: 'Visa', content: 'VISA' }
  ];

  window.JuacoStoreConfig = window.JuacoStoreConfig || {};
  window.JuacoStoreConfig.paymentMethods = paymentMethods;
  // Cada ruta conserva su propio footer, por eso se monta en cualquier bloque
  // de pagos del pie de página y no depende de HTML duplicado.
  document.querySelectorAll('.footer-bottom .payment, [data-payment-methods]').forEach(function (container) {
    container.setAttribute('data-payment-methods', '');
    container.innerHTML = paymentMethods.map(function (method) {
      return '<a class="payment-card payment-card-' + method.id + '" href="shop-checkout.html" aria-label="' + method.label + '">' + method.content + '</a>';
    }).join('');
  });
}());
