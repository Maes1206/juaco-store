/* Completa la vista Blog Details a partir del artículo elegido en el listado. */
(function () {
  'use strict';

  var params = new URLSearchParams(window.location.search);
  var article = window.JuacoBlogArticles && window.JuacoBlogArticles[params.get('articulo')];
  if (!article) return;

  document.title = article.title + ' | Nexus Luxury Footwear';
  document.querySelector('.page-header-content .title').textContent = 'Artículo';
  document.querySelector('.page-header-content .breadcrumb li:last-child').textContent = 'Artículo';

  var thumb = document.querySelector('.blog-details-thumb img');
  thumb.src = article.image;
  thumb.alt = article.title;
  thumb.width = 750;
  thumb.height = 459;

  document.querySelector('.blog-meta-post .post-date a').textContent = article.date;
  document.querySelector('.blog-meta-post .author-info a').textContent = article.author;
  document.querySelector('.blog-details-item .main-title').textContent = article.title;

  var firstSection = document.querySelector('.details-wrapper-style1');
  firstSection.querySelector('p').textContent = article.intro;
  firstSection.querySelector('blockquote p').textContent = article.quote;
  firstSection.querySelector('.user-name').textContent = article.author;
  firstSection.querySelectorAll(':scope > p')[1].textContent = article.body;

  var secondSection = document.querySelector('.details-wrapper-style2');
  var secondaryImage = secondSection.querySelector('.p-image-right');
  secondaryImage.src = article.image;
  secondaryImage.alt = article.title;
  secondSection.querySelector('span').textContent = article.body;
  secondSection.querySelector('.mb-25').textContent = article.intro;
  secondSection.querySelectorAll('p')[2].textContent = article.body;

  var tagList = document.querySelector('.tage-list');
  tagList.innerHTML = '<span>Etiquetas:</span> ' + article.tags.map(function (tag) {
    return '<a href="blog.html">' + tag + '</a>';
  }).join(', ');
}());
