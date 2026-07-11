/* Analiza imágenes locales, descarta el fondo claro y obtiene el color dominante. */
(function () {
  'use strict';

  var palette = [
    { id: 'negro', label: 'Negro', hex: '#111111' },
    { id: 'carbon', label: 'Gris carbón', hex: '#374151' },
    { id: 'gris', label: 'Gris', hex: '#7b8491' },
    { id: 'azul-marino', label: 'Azul marino', hex: '#172554' },
    { id: 'azul', label: 'Azul', hex: '#3b82c4' },
    { id: 'cafe', label: 'Café', hex: '#5b3a29' },
    { id: 'vinotinto', label: 'Vinotinto', hex: '#741b35' },
    { id: 'rojo', label: 'Rojo', hex: '#dc3f4f' },
    { id: 'naranja', label: 'Naranja', hex: '#e8922e' },
    { id: 'amarillo', label: 'Amarillo', hex: '#e4ca25' },
    { id: 'verde-oscuro', label: 'Verde oscuro', hex: '#174c3c' },
    { id: 'verde', label: 'Verde', hex: '#55bd82' },
    { id: 'morado', label: 'Morado', hex: '#845ec2' },
    { id: 'rosa', label: 'Rosa', hex: '#db7298' },
    { id: 'beige', label: 'Beige', hex: '#c5b98b' },
    { id: 'blanco', label: 'Blanco', hex: '#f1f1ef' }
  ];
  var neutralIds = ['negro', 'carbon', 'gris', 'beige', 'blanco'];
  var memoryCache = {};

  function hexToRgb(hex) {
    return {
      r: parseInt(hex.slice(1, 3), 16),
      g: parseInt(hex.slice(3, 5), 16),
      b: parseInt(hex.slice(5, 7), 16)
    };
  }

  function closestPaletteColor(rgb, allowedIds) {
    var candidates = allowedIds ? palette.filter(function (color) {
      return allowedIds.indexOf(color.id) !== -1;
    }) : palette;
    return candidates.reduce(function (closest, color) {
      var target = hexToRgb(color.hex);
      var redMean = (rgb.r + target.r) / 2;
      var redDifference = rgb.r - target.r;
      var greenDifference = rgb.g - target.g;
      var blueDifference = rgb.b - target.b;
      var distance = (2 + redMean / 256) * Math.pow(redDifference, 2) + 4 * Math.pow(greenDifference, 2) + (2 + (255 - redMean) / 256) * Math.pow(blueDifference, 2);
      return !closest || distance < closest.distance ? { color: color, distance: distance } : closest;
    }, null).color;
  }

  function readPersistentCache(src) {
    try {
      return JSON.parse(localStorage.getItem('juaco-color-v6:' + src));
    } catch (error) {
      return null;
    }
  }

  function savePersistentCache(src, analysis) {
    try {
      localStorage.setItem('juaco-color-v6:' + src, JSON.stringify(analysis));
    } catch (error) {
      return;
    }
  }

  function analyzeImage(src) {
    if (memoryCache[src]) return Promise.resolve(memoryCache[src]);
    var saved = readPersistentCache(src);
    if (saved) {
      memoryCache[src] = saved;
      return Promise.resolve(saved);
    }

    return new Promise(function (resolve, reject) {
      var image = new Image();
      image.onload = function () {
        try {
          var size = 72;
          var canvas = document.createElement('canvas');
          canvas.width = size;
          canvas.height = size;
          var context = canvas.getContext('2d', { willReadFrequently: true });
          context.drawImage(image, 0, 0, size, size);
          var pixels = context.getImageData(0, 0, size, size).data;
          var buckets = {};
          var validPixels = 0;

          for (var index = 0; index < pixels.length; index += 4) {
            var r = pixels[index];
            var g = pixels[index + 1];
            var b = pixels[index + 2];
            var alpha = pixels[index + 3];
            var max = Math.max(r, g, b);
            var min = Math.min(r, g, b);
            if (alpha < 128 || (min > 242) || (min > 225 && max - min < 14)) continue;

            var saturation = max === 0 ? 0 : (max - min) / max;
            var pixelCategory = saturation < 0.18
              ? closestPaletteColor({ r: r, g: g, b: b }, neutralIds)
              : closestPaletteColor({ r: r, g: g, b: b });
            var key = pixelCategory.id;
            if (!buckets[key]) buckets[key] = { count: 0, r: 0, g: 0, b: 0, category: pixelCategory };
            buckets[key].count += 1;
            buckets[key].r += r;
            buckets[key].g += g;
            buckets[key].b += b;
            validPixels += 1;
          }

          var rankedColors = Object.keys(buckets).map(function (key) {
            return buckets[key];
          }).sort(function (a, b) {
            return b.count - a.count;
          });
          var dominant = rankedColors[0];
          if (!dominant || !validPixels) throw new Error('La imagen no contiene suficientes píxeles analizables.');

          var rgb = {
            r: Math.round(dominant.r / dominant.count),
            g: Math.round(dominant.g / dominant.count),
            b: Math.round(dominant.b / dominant.count)
          };
          var category = dominant.category;
          var neutralColors = rankedColors.filter(function (bucket) {
            return neutralIds.indexOf(bucket.category.id) !== -1 && (bucket.count / validPixels) >= 0.02;
          });
          var chromaticColors = rankedColors.filter(function (bucket) {
            return neutralIds.indexOf(bucket.category.id) === -1 && (bucket.count / validPixels) >= 0.045;
          });
          var selectedBuckets = [];
          if (neutralColors.length) selectedBuckets.push(neutralColors[0]);
          chromaticColors.slice(0, 2).forEach(function (bucket) { selectedBuckets.push(bucket); });
          neutralColors.forEach(function (bucket) {
            if (selectedBuckets.length < 3 && selectedBuckets.indexOf(bucket) === -1) selectedBuckets.push(bucket);
          });

          var strongColors = selectedBuckets.slice(0, 3).map(function (bucket) {
            return {
              category: bucket.category.id,
              label: bucket.category.label,
              hex: bucket.category.hex,
              percentage: Math.round((bucket.count / validPixels) * 1000) / 10
            };
          });
          var analysis = {
            rgb: rgb,
            hex: '#' + [rgb.r, rgb.g, rgb.b].map(function (channel) { return channel.toString(16).padStart(2, '0'); }).join(''),
            percentage: Math.round((dominant.count / validPixels) * 1000) / 10,
            category: category.id,
            categoryLabel: category.label,
            colors: strongColors
          };
          memoryCache[src] = analysis;
          savePersistentCache(src, analysis);
          resolve(analysis);
        } catch (error) {
          reject(error);
        }
      };
      image.onerror = function () { reject(new Error('No se pudo analizar ' + src)); };
      image.src = src;
    });
  }

  function analyzeProducts(products) {
    return Promise.all(products.map(function (product) {
      return analyzeImage(product.image).then(function (analysis) {
        product.colorAnalysis = analysis;
        return product;
      }).catch(function () {
        product.colorAnalysis = null;
        return product;
      });
    }));
  }

  window.JuacoColorAnalyzer = {
    palette: palette,
    analyzeImage: analyzeImage,
    analyzeProducts: analyzeProducts
  };
}());
