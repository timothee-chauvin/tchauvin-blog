(function () {
  var COPY_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  var DONE_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>';

  document.querySelectorAll('.cite-box-status').forEach(function (s) { s.innerHTML = COPY_ICON; });

  var now = new Date();
  var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var pad = function (n) { return (n < 10 ? '0' : '') + n; };
  var human = now.getDate() + ' ' + months[now.getMonth()] + ' ' + now.getFullYear();
  var iso = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
  document.querySelectorAll('.cite-access-human').forEach(function (e) { e.textContent = human; });
  document.querySelectorAll('.cite-access-iso').forEach(function (e) { e.textContent = iso; });

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

  function copyBox(box) {
    if (box.classList.contains('is-copied')) return;
    var text = box.querySelector('.cite-copyable').textContent.trim();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
    } else {
      fallbackCopy(text);
    }
    var status = box.querySelector('.cite-box-status');
    var original = status.innerHTML;
    box.classList.add('is-copied');
    status.innerHTML = DONE_ICON + '<span class="cite-status-label">Copied</span>';
    setTimeout(function () {
      box.classList.remove('is-copied');
      status.innerHTML = original;
    }, 1500);
  }

  document.querySelectorAll('.cite-box').forEach(function (box) {
    box.addEventListener('click', function () { copyBox(box); });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); copyBox(box); }
    });
  });

  var dlg = document.getElementById('cite-dialog');
  var pill = document.querySelector('.cite-pill');
  if (dlg && pill && typeof dlg.showModal === 'function') {
    pill.addEventListener('click', function (e) { e.preventDefault(); dlg.showModal(); });
    var closeBtn = dlg.querySelector('.cite-dialog-close');
    if (closeBtn) closeBtn.addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
  }
})();
