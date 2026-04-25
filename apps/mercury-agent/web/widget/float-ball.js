(function () {
  if (window.__mcFloatBallLoaded) return;
  window.__mcFloatBallLoaded = true;

  function build() {
    const ball = document.createElement('button');
    ball.id = 'mc-float-ball';
    ball.title = 'Mercury';
    ball.innerHTML = '⚘';
    Object.assign(ball.style, { left: '85%', top: '85%' });

    const menu = document.createElement('div');
    menu.id = 'mc-menu';
    menu.innerHTML =
      '<button class="mc-menu-item" data-action="files">' +
      '  <span class="mc-icon">\u{1F4C1}</span> File Explorer' +
      '</button>';

    document.body.appendChild(ball);
    document.body.appendChild(menu);
    return { ball, menu };
  }

  function makeDraggable(ball, menu) {
    let dragging = false;
    let moved = false;
    let offX = 0;
    let offY = 0;
    ball.addEventListener('mousedown', (e) => {
      dragging = true;
      moved = false;
      const r = ball.getBoundingClientRect();
      offX = e.clientX - r.left;
      offY = e.clientY - r.top;
    });
    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      moved = true;
      ball.style.left = (e.clientX - offX) + 'px';
      ball.style.top = (e.clientY - offY) + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (dragging && !moved) toggleMenu(menu, ball);
      dragging = false;
    });
  }

  function toggleMenu(menu, ball) {
    const open = menu.classList.toggle('open');
    if (!open) return;
    const r = ball.getBoundingClientRect();
    let top = r.top - menu.offsetHeight - 4;
    if (top < 4) top = r.bottom + 4;
    menu.style.left = r.left + 'px';
    menu.style.top = top + 'px';
  }

  function openIframe(src, title) {
    const existing = document.getElementById('mc-iframe-modal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'mc-iframe-modal';
    modal.innerHTML =
      '<div class="mc-iframe-box"><div class="mc-iframe-header">' +
      '<span>' + (title || 'Mercury') + '</span>' +
      '<button class="mc-iframe-close" id="mc-iframe-close">✕</button>' +
      '</div><iframe src="' + src + '"></iframe></div>';
    document.body.appendChild(modal);
    document.getElementById('mc-iframe-close').onclick = () => modal.remove();
  }

  function bindMenu(menu) {
    menu.addEventListener('click', (e) => {
      const item = e.target.closest('[data-action]');
      if (!item) return;
      menu.classList.remove('open');
      if (item.dataset.action === 'files') {
        openIframe('/explorer/', 'File Explorer');
      }
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#mc-menu') && !e.target.closest('#mc-float-ball')) {
        menu.classList.remove('open');
      }
    });
  }

  function init() {
    const { ball, menu } = build();
    makeDraggable(ball, menu);
    bindMenu(menu);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
