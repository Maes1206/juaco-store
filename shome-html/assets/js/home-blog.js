(function () {
  'use strict';

  var container = document.getElementById('latest-posts');
  if (!container) return;

  var revealObserver = null;
  if ('IntersectionObserver' in window) {
    revealObserver = new IntersectionObserver(function (entries, observer) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
  }

  function reveal(node, delay) {
    node.classList.add('blog-entry');
    node.style.transitionDelay = delay + 'ms';
    if (revealObserver) {
      revealObserver.observe(node);
    } else {
      node.classList.add('is-visible');
    }
  }

  var sectionTitle = document.querySelector('.latest-news-section .section-title');
  if (sectionTitle) reveal(sectionTitle, 0);

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function link(url, className, text) {
    var node = element('a', className, text);
    node.href = url;
    return node;
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat('es-CO', {
      day: '2-digit', month: 'short', year: 'numeric'
    }).format(new Date(value + 'T00:00:00'));
  }

  function renderPost(post) {
    var column = element('div', 'col-md-6 col-lg-4');
    var item = element('article', 'post-item');
    var content = element('div', 'inner-content');
    var thumb = element('div', 'thumb');
    var imageLink = link(post.url);
    var image = document.createElement('img');
    image.src = post.image;
    image.width = 370;
    image.height = 260;
    image.alt = post.alt || post.title;
    image.loading = 'lazy';
    imageLink.appendChild(image);
    thumb.appendChild(imageLink);

    var body = element('div', 'content');
    var meta = element('div', 'meta-post');
    var list = element('ul');
    var date = element('li', 'post-date');
    date.appendChild(element('i', 'fa fa-calendar'));
    date.appendChild(link('blog.html', '', formatDate(post.publishedAt)));
    var author = element('li', 'author-info');
    author.appendChild(element('i', 'fa fa-user'));
    author.appendChild(link('blog.html', '', post.author));
    list.appendChild(date);
    list.appendChild(author);
    meta.appendChild(list);
    body.appendChild(meta);

    var title = element('h4', 'title');
    title.appendChild(link(post.url, '', post.title));
    body.appendChild(title);
    body.appendChild(link(post.url, 'post-btn', 'Leer más'));

    content.appendChild(thumb);
    content.appendChild(body);
    item.appendChild(content);
    column.appendChild(item);
    return column;
  }

  var posts = window.JUACO_BLOG_POSTS;
  if (!Array.isArray(posts)) {
    container.appendChild(element('p', 'text-center', 'No fue posible cargar las noticias.'));
    return;
  }

  posts.slice(0, 3).forEach(function (post, index) {
    var card = renderPost(post);
    container.appendChild(card);
    reveal(card, 160 + (index * 120));
  });
}());
