(function($) {
  
  "use strict";

  // Background Image Js
    const bgSelector = $("[data-bg-img]");
    bgSelector.each(function (index, elem) {
      let element = $(elem),
        bgSource = element.data('bg-img');
      element.css('background-image', 'url(' + bgSource + ')');
    });

  // Background Color Js
    const Bgcolorcl = $("[data-bg-color]");
    Bgcolorcl.each(function (index, elem) {
      let element = $(elem),
        Bgcolor = element.data('bg-color');
      element.css('background-color', Bgcolor);
    });

  // Margin Top Js
    $('[data-margin-top]').each(function() {
      $(this).css('margin-top', $(this).data("margin-top"));
    });

  // Margin Bottom Js
    $('[data-margin-bottom]').each(function() {
      $(this).css('margin-bottom', $(this).data("margin-bottom"));
    });

  // Offcanvas Nav Js
    var $offCanvasNav = $('.mobile-menu-items'),
    $offCanvasNavSubMenu = $offCanvasNav.find('.sub-menu');

    /*Add Toggle Button With Off Canvas Sub Menu*/
    $offCanvasNavSubMenu.parent().prepend('<span class="mobile-menu-expand"></span>');

    /*Close Off Canvas Sub Menu*/
    $offCanvasNavSubMenu.slideUp();

    /*Category Sub Menu Toggle*/
    $offCanvasNav.on('click', 'li a, li .mobile-menu-expand, li .menu-title', function(e) {
      var $this = $(this);
      if($this.parent().attr('class')){
        if (($this.parent().attr('class').match(/\b(menu-item-has-children|has-children|has-sub-menu)\b/)) && ($this.attr('href') === '#' || $this.hasClass('mobile-menu-expand'))) {
          e.preventDefault();
          if ($this.siblings('ul:visible').length) {
            $this.parent('li').removeClass('active-expand');
            $this.siblings('ul').slideUp();
          } else {
            $this.parent('li').addClass('active-expand');
            $this.closest('li').siblings('li').find('ul:visible').slideUp();
            $this.closest('li').siblings('li').removeClass('active-expand');
            $this.siblings('ul').slideDown();
          }
        }
      }
    });

    $( ".sub-menu" ).parent( "li" ).addClass( "menu-item-has-children" );

  // Menu Activeion Js
    var cururl = window.location.pathname;
    var curpage = cururl.substr(cururl.lastIndexOf('/') + 1);
    var hash = window.location.hash.substr(1);
    if((curpage === "" || curpage === "/" || curpage === "admin") && hash === "")
      {
      } else {
        $(".header-navigation-area li").each(function()
      {
        $(this).removeClass("active");
      });
      if(hash != "")
        $(".header-navigation-area li a[href='"+hash+"']").parents("li").addClass("active");
      else
      $(".header-navigation-area li a[href='"+curpage+"']").parents("li").addClass("active");
    }
    
  // Popup Quick View JS
    var popupProduct = $(".product-quick-view-modal");
    $(".btn-product-quick-view-open").on('click', function() {
      popupProduct.addClass('active');
      $("body").addClass("fix");
    });
    $(".btn-close, .canvas-overlay").on('click', function() {
      popupProduct.removeClass('active');
      $("body").removeClass("fix");
    });

  // Swiper Default Slider Js
    var mainlSlider = new Swiper('.default-slider-container', {
      slidesPerView : 1,
      slidesPerGroup: 1,
      loop: true,
      speed: 500,
      spaceBetween: 0,
      effect: 'fade',
      autoHeight: true, //enable auto height
      autoplay: {
        delay: 6000,
        disableOnInteraction: false,
      },
      fadeEffect: {
          crossFade: true,
      },
      navigation: {
        nextEl: '.default-slider-container .swiper-btn-next',
        prevEl: '.default-slider-container .swiper-btn-prev',
      },
    });

  // Product Single Thumb Slider Js
    var ProductNav = new Swiper('.single-product-nav-slider', {
      spaceBetween: 21,
      slidesPerView: 4,
    });
    var ProductThumb = new Swiper('.single-product-thumb-slider', {
      effect: 'fade',
      fadeEffect: {
        crossFade: true,
      },
      thumbs: {
        swiper: ProductNav,
      }
    });

  // Product Slider Col4 Js
    var productSliderCol4 = new Swiper('.product-slider-col4-container', {
      slidesPerView : 4,
      slidesPerGroup: 1,
      allowTouchMove: true,
      autoplay: {
        delay: 4200,
        disableOnInteraction: false,
        pauseOnMouseEnter: true,
      },
      grabCursor: true,
      loop: true,
      spaceBetween: 30,
      speed: 800,
      navigation: {
        nextEl: '.product-swiper-btn-next',
        prevEl: '.product-swiper-btn-prev',
      },
      breakpoints: {
        1400: {
          slidesPerView : 4,
          spaceBetween: 30,
        },
        1200: {
          slidesPerView : 4,
          spaceBetween: 30,
          allowTouchMove: true,
        },
        992: {
          slidesPerView : 3,
          spaceBetween: 30,
          allowTouchMove: true,
        },
        576: {
          slidesPerView : 2,
          spaceBetween: 30,
          allowTouchMove: true,
        },
        0: {
          slidesPerView : 1,
          spaceBetween: 30,
          allowTouchMove: true,
        },
      }
    });

  // Product Slider Col4 Js
    var testimonialSlider = new Swiper('.testimonial-slider-container', {
      slidesPerView : 2,
      slidesPerGroup: 1,
      allowTouchMove: false,
      spaceBetween: 30,
      speed: 600,
      breakpoints: {
        1200: {
          slidesPerView : 2,
          spaceBetween: 30,
        },
        992: {
          slidesPerView : 1,
          spaceBetween: 30,
        },
        0: {
          slidesPerView : 1,
          spaceBetween: 30,
          allowTouchMove: true,
        },
      }
    });

  // Fancybox Js
    $('.image-popup').fancybox();
    $('.video-popup').fancybox();

  // Aos Js
    AOS.init({
      once: true,
      duration: 1200,
    });

  // Parallax Scene Js
    $('.scene').each(function () {
      new Parallax($(this)[0]);
    });
  // Parallax Js
    $('.parallax').jarallax({
        // Element jarallax Parallax
    });

  // Product Quantity JS
    var proQty = $(".pro-qty");
    proQty.append('<div class= "dec qty-btn">-</div>');
    proQty.append('<div class="inc qty-btn">+</div>');
  $('.qty-btn').on('click', function (e) {
      e.preventDefault();
      var $button = $(this);
      var oldValue = $button.parent().find('input').val();
      if ($button.hasClass('inc')) {
        var newVal = parseFloat(oldValue) + 1;
      } else {
        // Don't allow decrementing below zero
        if (oldValue > 1) {
          var newVal = parseFloat(oldValue) - 1;
        } else {
          newVal = 1;
        }
      }
      $button.parent().find('input').val(newVal);
      $(this).closest('.shopping-cart-area').trigger('cart:updated');
    });

  // Carrito dinamico: eliminar productos, vaciar el carrito y recalcular totales.
  var $cartArea = $('.shopping-cart-area');
  if ($cartArea.length) {
    var formatCop = function (value) {
      return '$' + Math.round(value).toLocaleString('es-CO') + ' COP';
    };

    var updateCart = function () {
      var total = 0;
      var itemCount = 0;
      var $items = $cartArea.find('tbody .cart-product-item');

      $items.each(function () {
        var $item = $(this);
        var price = parseInt(($item.find('.product-price .price').text() || '').replace(/[^0-9]/g, ''), 10) || 0;
        var quantity = parseInt($item.find('.quantity').val(), 10) || 1;
        quantity = Math.max(1, quantity);
        $item.find('.quantity').val(quantity);
        $item.find('.product-subtotal .price').text(formatCop(price * quantity));
        total += price * quantity;
        itemCount += quantity;
      });

      $cartArea.find('.cart-subtotal .price, .order-total .price').text(formatCop(total));
      $('.shop-count').text(String(itemCount).padStart(2, '0'));

      var $freeShipping = $cartArea.find('#radio2');
      var $fixedShipping = $cartArea.find('#radio1');
      var freeShippingThreshold = parseInt($freeShipping.data('free-shipping-threshold'), 10) || 400000;
      var freeShippingAvailable = total > freeShippingThreshold;
      $freeShipping.prop('disabled', !freeShippingAvailable);
      $freeShipping.closest('li').toggleClass('is-available', freeShippingAvailable);
      if (freeShippingAvailable) {
        $freeShipping.prop('checked', true);
        $fixedShipping.prop('checked', false);
      } else {
        $freeShipping.prop('checked', false);
        $fixedShipping.prop('checked', true);
      }

      var $emptyRow = $cartArea.find('.cart-empty-row');
      if (!$items.length) {
        if (!$emptyRow.length) {
          $cartArea.find('tbody').prepend('<tr class="cart-empty-row"><td colspan="6">Tu carrito está vacío.</td></tr>');
        }
        $cartArea.find('.actions').hide();
      } else {
        $emptyRow.remove();
        $cartArea.find('.actions').show();
      }
    };

    $cartArea.on('click', '.product-remove a', function (event) {
      event.preventDefault();
      $(this).closest('.cart-product-item').fadeOut(220, function () {
        $(this).remove();
        updateCart();
      });
    });

    $cartArea.on('input change', '.quantity', updateCart);
    $cartArea.on('cart:updated', updateCart);
    $cartArea.on('click', '.clear-cart', function (event) {
      event.preventDefault();
      $cartArea.find('.cart-product-item').remove();
      updateCart();
    });

    updateCart();
  }

  // Zoom de detalle en la imagen principal de producto.
  var productZoomSlides = document.querySelectorAll('.product-single-thumb .single-product-thumb .swiper-slide');
  if (productZoomSlides.length && window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    productZoomSlides.forEach(function (slide) {
      var image = slide.querySelector('img');
      if (!image) return;

      slide.addEventListener('mouseenter', function () {
        slide.classList.add('is-zooming');
      });

      slide.addEventListener('mousemove', function (event) {
        var bounds = slide.getBoundingClientRect();
        var x = ((event.clientX - bounds.left) / bounds.width) * 100;
        var y = ((event.clientY - bounds.top) / bounds.height) * 100;
        image.style.transformOrigin = x + '% ' + y + '%';
      });

      slide.addEventListener('mouseleave', function () {
        slide.classList.remove('is-zooming');
        image.style.transformOrigin = 'center center';
      });
    });
  }

  // Slider Range Js
    $('#price-range').slider({
      range: true,
      min: 0,
      max: 350,
      values: [ 16, 300 ],
      slide: function( event, ui ) {
        $('.ui-slider-handle:eq(0)').html( '<span>' + '$' + ui.values[ 0 ] + '</span>');
        $('.ui-slider-handle:eq(1)').html( '<span>' + '$' + ui.values[ 1 ] + '</span>');
      }
    });
    $('.ui-slider-handle:eq(0)').html( '<span>' + '$' + $( "#price-range" ).slider( "values", 0 ) + '</span>' );
    $('.ui-slider-handle:eq(1)').html( '<span>' + '$' + $( "#price-range" ).slider( "values", 1 ) + '</span>' );
    
  // Review Form JS
    $(".review-write-btn").on('click', function() {
      $(".reviews-form-area, .review-write-btn").toggleClass("show").focus();
    });

  // Ajax Contact Form JS
    var form = $('#contact-form');
    var formMessages = $('.form-message');

    $(form).submit(function(e) {
      e.preventDefault();
      var formData = form.serialize();
      $.ajax({
        type: 'POST',
        url: form.attr('action'),
        data: formData
      }).done(function(response) {
        // Make sure that the formMessages div has the 'success' class.
        $(formMessages).removeClass('alert alert-danger');
        $(formMessages).addClass('alert alert-success fade show');

        // Set the message text.
        formMessages.html("<button type='button' class='btn-close' data-bs-dismiss='alert'>&times;</button>");
        formMessages.append(response);

        // Clear the form.
        $('#contact-form input,#contact-form textarea').val('');
      }).fail(function(data) {
        // Make sure that the formMessages div has the 'error' class.
        $(formMessages).removeClass('alert alert-success');
        $(formMessages).addClass('alert alert-danger fade show');

        // Set the message text.
        if (data.responseText === '') {
          formMessages.html("<button type='button' class='btn-close' data-bs-dismiss='alert'>&times;</button>");
          formMessages.append(data.responseText);
        } else {
          $(formMessages).text('Oops! An error occurred and your message could not be sent.');
        }
      });
    });

  // scrollToTop Js
    var featuredProducts = document.querySelectorAll('.featured-products-section .product-item');
    if (featuredProducts.length) {
      var revealProduct = function(product) {
        product.classList.add('is-visible');
      };

      if ('IntersectionObserver' in window) {
        var productObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealProduct(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.12 });

        featuredProducts.forEach(function(product, index) {
          product.classList.add('product-entry');
          product.style.transitionDelay = Math.min(index * 90, 450) + 'ms';
          productObserver.observe(product);
        });
      } else {
        featuredProducts.forEach(function(product) {
          product.classList.add('product-entry');
          revealProduct(product);
        });
      }
    }

    var bestSellerElements = document.querySelectorAll('.best-seller-section .section-title, .best-seller-section .product-slider-wrap');
    if (bestSellerElements.length) {
      var revealBestSeller = function(element) {
        element.classList.add('is-visible');
      };

      if ('IntersectionObserver' in window) {
        var bestSellerObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealBestSeller(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.15 });

        bestSellerElements.forEach(function(element, index) {
          element.classList.add('best-seller-entry');
          element.style.transitionDelay = (index * 140) + 'ms';
          bestSellerObserver.observe(element);
        });
      } else {
        bestSellerElements.forEach(function(element) {
          element.classList.add('best-seller-entry');
          revealBestSeller(element);
        });
      }
    }

    var categoryPromoItems = document.querySelectorAll('.category-promo-section .divider-thumb-content > .thumb, .category-promo-section .promo-extra-thumb');
    if (categoryPromoItems.length) {
      var revealCategoryPromo = function(element) {
        element.classList.add('is-visible');
      };

      if ('IntersectionObserver' in window) {
        var categoryPromoObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealCategoryPromo(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.12 });

        categoryPromoItems.forEach(function(element, index) {
          element.classList.add('category-promo-entry');
          element.style.transitionDelay = (index * 130) + 'ms';
          categoryPromoObserver.observe(element);
        });
      } else {
        categoryPromoItems.forEach(function(element) {
          element.classList.add('category-promo-entry');
          revealCategoryPromo(element);
        });
      }
    }

    var collectionItems = document.querySelectorAll('.collection-entry-section .product-collection, .collection-feature-section .feature-content-box');
    if (collectionItems.length) {
      var revealCollection = function(element) {
        window.requestAnimationFrame(function() {
          window.requestAnimationFrame(function() {
            element.classList.add('is-visible');
          });
        });
      };

      if ('IntersectionObserver' in window) {
        var collectionObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealCollection(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.15 });

        collectionItems.forEach(function(element, index) {
          element.classList.add('collection-entry');
          element.style.transitionDelay = (index * 130) + 'ms';
          collectionObserver.observe(element);
        });
      } else {
        collectionItems.forEach(function(element) {
          element.classList.add('collection-entry');
          revealCollection(element);
        });
      }
    }

    var aboutStoreLogo = document.querySelector('.about-store-logo');
    if (aboutStoreLogo) {
      var revealAboutLogo = function() {
        window.requestAnimationFrame(function() {
          window.requestAnimationFrame(function() {
            aboutStoreLogo.classList.add('is-visible');
          });
        });
      };

      aboutStoreLogo.classList.add('about-logo-entry');
      if ('IntersectionObserver' in window) {
        var aboutLogoObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealAboutLogo();
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.2 });
        aboutLogoObserver.observe(aboutStoreLogo);
      } else {
        revealAboutLogo();
      }
    }

    var teamElements = document.querySelectorAll('.team-area .section-title, .team-area .team-item');
    if (teamElements.length) {
      var revealTeam = function(element) {
        window.requestAnimationFrame(function() {
          window.requestAnimationFrame(function() {
            element.classList.add('is-visible');
          });
        });
      };

      if ('IntersectionObserver' in window) {
        var teamObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealTeam(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.15 });

        teamElements.forEach(function(element, index) {
          element.classList.add('team-entry');
          element.style.transitionDelay = (index * 140) + 'ms';
          teamObserver.observe(element);
        });
      } else {
        teamElements.forEach(function(element) {
          element.classList.add('team-entry');
          revealTeam(element);
        });
      }
    }

    var testimonialElements = document.querySelectorAll('.testimonial-area .section-title, .testimonial-area .testimonial-slider-container');
    if (testimonialElements.length) {
      var revealTestimonial = function(element) {
        window.requestAnimationFrame(function() {
          window.requestAnimationFrame(function() {
            element.classList.add('is-visible');
          });
        });
      };

      if ('IntersectionObserver' in window) {
        var testimonialObserver = new IntersectionObserver(function(entries, observer) {
          entries.forEach(function(entry) {
            if (entry.isIntersecting) {
              revealTestimonial(entry.target);
              observer.unobserve(entry.target);
            }
          });
        }, { threshold: 0.15 });

        testimonialElements.forEach(function(element, index) {
          element.classList.add('testimonial-entry');
          element.style.transitionDelay = (index * 140) + 'ms';
          testimonialObserver.observe(element);
        });
      } else {
        testimonialElements.forEach(function(element) {
          element.classList.add('testimonial-entry');
          revealTestimonial(element);
        });
      }
    }

    function scrollToTop() {
      var $scrollUp = $('#scroll-to-top'),
        $lastScrollTop = 0,
        $window = $(window);
        $window.on('scroll', function () {
        var st = $(this).scrollTop();
          if (st > $lastScrollTop) {
              $scrollUp.removeClass('show');
          } else {
            if ($window.scrollTop() > 120) {
              $scrollUp.addClass('show');
            } else {
              $scrollUp.removeClass('show');
            }
          }
          $lastScrollTop = st;
      });
      $scrollUp.on('click', function (evt) {
        $('html, body').animate({scrollTop: 0}, 50);
        evt.preventDefault();
      });
    }
    scrollToTop();

})(window.jQuery);
