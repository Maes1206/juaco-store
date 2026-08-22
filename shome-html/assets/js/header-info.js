/* Información compartida por las cabeceras, cargada desde la fuente de datos. */
(function () {
  'use strict';

  function applySession(headerItems, session) {
    return headerItems.map(function (item) {
      if (item.kind === 'account' && session) {
        return Object.assign({}, item, { label: session.label, href: session.href });
      }
      return item;
    });
  }

  // El nombre lo escribe la persona al registrarse, asi que se escapa antes de
  // insertarlo como HTML.
  var HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return HTML_ESCAPES[character];
    });
  }

  function greetingMarkup(session) {
    if (!session || !session.authenticated || !session.greeting) return '';
    var name = session.username || '';
    return '<li class="account-greeting">Hola, <strong>' + escapeHtml(name) + '</strong></li>';
  }

  function renderHeader(headerItems, session) {
    document.querySelectorAll('[data-header-info], .header-top .header-info-items .info-items').forEach(function (container) {
      // Se reemplaza la lista completa, asi que el saludo se vuelve a incluir
      // aqui aunque el servidor ya lo hubiera pintado.
      container.innerHTML = '<ul>' + greetingMarkup(session) + headerItems.map(function (item) {
        return '<li class="' + item.kind + '"><i class="fa ' + item.icon + '"></i><a href="' + item.href + '">' + item.label + '</a></li>';
      }).join('') + '</ul>';
    });
  }

  function updateAccountLinks(session) {
    if (!session) return;
    // Menú lateral móvil u otros enlaces de cuenta estáticos.
    document.querySelectorAll('.off-canvas-wrapper .info-items li.account a').forEach(function (link) {
      link.setAttribute('href', session.href);
      var icon = link.querySelector('i');
      link.textContent = session.label;
      if (icon) link.insertBefore(icon, link.firstChild);
    });

    var greeting = greetingMarkup(session);
    if (!greeting) return;
    document.querySelectorAll('.off-canvas-wrapper .info-items ul').forEach(function (list) {
      // Las plantillas que ya lo traen del servidor no deben duplicarlo.
      if (list.querySelector('.account-greeting')) return;
      list.insertAdjacentHTML('afterbegin', greeting);
    });
  }

  Promise.all([
    fetch('assets/data/store-info.json').then(function (r) {
      if (!r.ok) throw new Error('No se pudo cargar la información de tienda.');
      return r.json();
    }),
    fetch('api/session/', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; }),
  ])
    .then(function (results) {
      var storeInfo = results[0];
      var session = results[1];
      var headerItems = applySession(storeInfo.headerItems || [], session);
      window.JuacoStoreConfig = window.JuacoStoreConfig || {};
      window.JuacoStoreConfig.headerItems = headerItems;
      window.JuacoStoreConfig.session = session;
      renderHeader(headerItems, session);
      updateAccountLinks(session);
    })
    .catch(function (error) {
      console.warn(error.message);
    });
}());
