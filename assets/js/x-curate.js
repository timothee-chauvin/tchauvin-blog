// Owner-only curation and sync controls; see _includes/x_curate.html for the
// security model.
(function () {
  // #curate is the mobile setup path (no devtools console there); #curate-off forgets.
  if (location.hash === '#curate-off') localStorage.removeItem('x-curate-token');
  if (location.hash === '#curate' && !localStorage.getItem('x-curate-token')) {
    var entered = prompt('GitHub fine-grained PAT (Actions rw on this repo):');
    if (entered) localStorage.setItem('x-curate-token', entered.trim());
  }
  var token = localStorage.getItem('x-curate-token');
  if (!token) return;

  var REPO = 'https://api.github.com/repos/timothee-chauvin/tchauvin.com';
  var staged = {}; // id -> desired curated state, only where it differs from the page
  var bars = [];

  function gh(url, options) {
    options = options || {};
    options.headers = { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' };
    return fetch(url, options).then(function (res) {
      if (!res.ok) throw new Error('GitHub API ' + res.status);
      return res.status === 204 ? null : res.json();
    });
  }

  function dispatch(workflow, inputs) {
    return gh(REPO + '/actions/workflows/' + workflow + '/dispatches', {
      method: 'POST',
      body: JSON.stringify({ ref: 'gh-pages', inputs: inputs || {} })
    });
  }

  function pushCuration(status) {
    var add = [], remove = [];
    Object.keys(staged).forEach(function (id) { (staged[id] ? add : remove).push(id); });
    status.textContent = 'dispatching…';
    dispatch('curate.yml', { add: add.join(','), remove: remove.join(',') }).then(function () {
      staged = {};
      render();
      status.textContent = 'dispatched — site rebuilds in ~2 min';
    }).catch(function (err) {
      status.textContent = err.message;
    });
  }

  function syncNow(status) {
    status.textContent = 'dispatching…';
    dispatch('x-sync.yml').then(function () {
      status.textContent = 'sync dispatched — check the Actions tab';
    }).catch(function (err) {
      status.textContent = err.message;
    });
  }

  function render() {
    var n = Object.keys(staged).length;
    bars.forEach(function (bar) {
      bar.push.textContent = 'Push ' + n + ' curation change' + (n === 1 ? '' : 's');
      bar.push.disabled = n === 0;
    });
  }

  function makeBar() {
    var bar = document.createElement('div');
    bar.className = 'x-curate-bar';
    var push = document.createElement('button');
    push.type = 'button';
    var sync = document.createElement('button');
    sync.type = 'button';
    sync.textContent = 'Sync from X now';
    var status = document.createElement('span');
    status.className = 'x-curate-bar__status';
    push.addEventListener('click', function () { pushCuration(status); });
    sync.addEventListener('click', function () { syncNow(status); });
    bar.append(push, sync, status);
    bars.push({ push: push });
    return bar;
  }

  document.querySelectorAll('article.x-post--main').forEach(function (card) {
    var link = card.querySelector('a.x-post__date');
    var match = link && link.href.match(/\/status\/(\d+)/);
    if (!match) return;
    var id = match[1];
    var star = card.querySelector('.x-curate-star');
    if (!star) {
      star = document.createElement('span');
      star.className = 'x-curate-star';
      star.textContent = '☆';
      card.querySelector('.x-post__meta').appendChild(star);
    }
    var base = star.classList.contains('is-on');
    star.classList.add('is-toggle');
    star.addEventListener('click', function () {
      var on = star.classList.toggle('is-on');
      star.textContent = on ? '★' : '☆';
      if (on === base) delete staged[id]; else staged[id] = on;
      render();
    });
  });

  var archive = document.querySelector('.x-archive');
  if (archive) {
    archive.prepend(makeBar());
    archive.append(makeBar());
    render();
  }
})();
