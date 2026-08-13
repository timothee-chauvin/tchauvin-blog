(function () {
  var DONE_ICON = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>';

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
    }
    fallbackCopy(text);
    return Promise.resolve();
  }

  document.querySelectorAll('button.copy-pill').forEach(function (btn) {
    var icon = btn.querySelector('.copy-pill-icon');
    var label = btn.querySelector('.copy-pill-label');
    var originalIcon = icon.innerHTML;
    var originalLabel = label.textContent;
    var timer;

    function flash(labelText, isError, iconHtml) {
      if (iconHtml != null) icon.innerHTML = iconHtml;
      label.textContent = labelText;
      btn.classList.toggle('is-error', isError);
      clearTimeout(timer);
      timer = setTimeout(function () {
        icon.innerHTML = originalIcon;
        label.textContent = originalLabel;
        btn.classList.remove('is-error');
      }, 1500);
    }

    btn.addEventListener('click', function () {
      fetch(btn.dataset.src).then(function (res) {
        if (!res.ok) throw new Error('fetch ' + btn.dataset.src + ' -> ' + res.status);
        return res.text();
      }).then(function (text) {
        return copyText(text);
      }).then(function () {
        flash('Copied', false, DONE_ICON);
      }).catch(function (err) {
        console.error('copy-llm:', err);
        flash('Copy failed', true, null);
      });
    });
  });
})();
