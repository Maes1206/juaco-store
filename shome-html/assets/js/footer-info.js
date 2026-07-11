/* Contenido compartido del pie de página: evita datos de plantilla. */
(function () {
  'use strict';

  document.querySelectorAll('.footer-area').forEach(function (footer) {
    footer.querySelectorAll('.social-icons').forEach(function (socialIcons) {
      socialIcons.remove();
    });

    footer.querySelectorAll('.widget-contact-wrap').forEach(function (contactWrap) {
      contactWrap.innerHTML = '<ul>' +
        '<li><span>Cobertura:</span> Envíos a toda Colombia.</li>' +
        '<li><span>Envío gratis:</span> Desde $400.000 COP.</li>' +
        '<li><span>Asesoría:</span> <a href="contact.html">Contáctanos aquí</a></li>' +
        '<li><a href="contact.html">Ver canales de atención</a></li>' +
      '</ul>';

      var widget = contactWrap.closest('.widget-item');
      if (!widget) return;
      var title = widget.querySelector('.widget-title');
      var collapsedTitle = widget.querySelector('.widget-collapsed-title');
      if (title) title.textContent = 'Información de compra';
      if (collapsedTitle) collapsedTitle.textContent = 'Información de compra';
    });
  });
}());
