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
  document.querySelectorAll('[data-payment-methods]').forEach(function (container) {
    container.innerHTML = paymentMethods.map(function (method) {
      return '<a class="payment-card payment-card-' + method.id + '" href="shop-checkout.html" aria-label="' + method.label + '">' + method.content + '</a>';
    }).join('');
  });
}());
