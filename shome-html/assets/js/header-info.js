/* Información compartida por las cabeceras, cargada desde la fuente de datos. */
(function () {
  'use strict';

  fetch('assets/data/store-info.json')
    .then(function (response) {
      if (!response.ok) throw new Error('No se pudo cargar la información de tienda.');
      return response.json();
    })
    .then(function (storeInfo) {
      var headerItems = storeInfo.headerItems || [];
      window.JuacoStoreConfig = window.JuacoStoreConfig || {};
      window.JuacoStoreConfig.headerItems = headerItems;
      document.querySelectorAll('[data-header-info], .header-top .header-info-items .info-items').forEach(function (container) {
        container.innerHTML = '<ul>' + headerItems.map(function (item) {
          return '<li class="' + item.kind + '"><i class="fa ' + item.icon + '"></i><a href="' + item.href + '">' + item.label + '</a></li>';
        }).join('') + '</ul>';
      });
    })
    .catch(function (error) {
      console.warn(error.message);
    });
}());
