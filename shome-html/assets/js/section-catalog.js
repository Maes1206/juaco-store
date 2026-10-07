/* Barra lateral de las secciones de marca.
   Los filtros de talla y color son enlaces normales, asi que funcionan sin
   JavaScript. Aqui se cubre lo que sin ayuda no navegaria: el selector de
   orden y el deslizador de precio. Si el deslizador no se puede montar se
   dejan visibles los campos numericos, que envian el mismo formulario. */
(function () {
  'use strict';

  function catalogUrl(changes) {
    var params = new URLSearchParams(window.location.search);
    params.delete('pagina');
    Object.keys(changes).forEach(function (key) {
      if (changes[key] === null) {
        params.delete(key);
      } else {
        params.set(key, changes[key]);
      }
    });
    var query = params.toString();
    return window.location.pathname + (query ? '?' + query : '') + '#catalog-products';
  }

  function formatCop(value) {
    return '$' + Number(value).toLocaleString('es-CO');
  }

  var sortSelect = document.querySelector('[data-catalog-sort]');
  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      window.location.href = catalogUrl({
        orden: sortSelect.value === 'default' ? null : sortSelect.value
      });
    });
  }

  var priceForm = document.querySelector('[data-catalog-price-filter]');
  if (!priceForm) return;

  var minInput = priceForm.querySelector('#price-min-input');
  var maxInput = priceForm.querySelector('#price-max-input');
  var minLabel = priceForm.querySelector('#price-min-label');
  var maxLabel = priceForm.querySelector('#price-max-label');
  var slider = priceForm.querySelector('#price-range');
  var floor = Number(priceForm.dataset.floor);
  var ceiling = Number(priceForm.dataset.ceiling);

  // Sin el deslizador el formulario sigue sirviendo: solo se ordena el rango
  // para que un "desde" mayor que el "hasta" no devuelva cero resultados.
  priceForm.addEventListener('submit', function () {
    if (minInput && maxInput && Number(minInput.value) > Number(maxInput.value)) {
      var swap = minInput.value;
      minInput.value = maxInput.value;
      maxInput.value = swap;
    }
  });

  var canUseSlider = window.jQuery && window.jQuery.fn.slider && slider && floor < ceiling;
  if (!canUseSlider) return;

  window.jQuery(slider).slider({
    range: true,
    min: floor,
    max: ceiling,
    step: 1000,
    values: [Number(minInput.value) || floor, Number(maxInput.value) || ceiling],
    slide: function (event, ui) {
      minLabel.textContent = 'Desde ' + formatCop(ui.values[0]);
      maxLabel.textContent = 'Hasta ' + formatCop(ui.values[1]);
    },
    stop: function (event, ui) {
      window.location.href = catalogUrl({ precioMin: ui.values[0], precioMax: ui.values[1] });
    }
  });
  priceForm.classList.add('has-slider');
}());
