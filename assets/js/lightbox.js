// Enlarge-on-click for post images. A post opts in by adding a .lightbox-overlay
// div (containing an #lightbox-img) and loading this script.
(function () {
  function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.querySelector('.lightbox-overlay').classList.add('active');
  }
  document.addEventListener('DOMContentLoaded', function () {
    var overlay = document.querySelector('.lightbox-overlay');
    if (!overlay) return;
    overlay.addEventListener('click', function () { overlay.classList.remove('active'); });
    document.querySelectorAll('.post-content img:not(#lightbox-img)').forEach(function (img) {
      img.style.cursor = 'pointer';
      img.addEventListener('click', function () { openLightbox(this.src); });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') overlay.classList.remove('active');
    });
  });
})();
