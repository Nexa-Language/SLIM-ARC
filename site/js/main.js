(() => {
  const header = document.querySelector('[data-header]');
  const nav = document.querySelector('.site-nav');
  const toggle = document.querySelector('.nav-toggle');
  const navLinks = [...document.querySelectorAll('.site-nav a[href^="#"]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const syncHeader = () => {
    header?.classList.toggle('scrolled', window.scrollY > 24);
  };

  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });

  toggle?.addEventListener('click', () => {
    const open = !nav?.classList.contains('open');
    nav?.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
  });

  navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      nav?.classList.remove('open');
      toggle?.setAttribute('aria-expanded', 'false');
    });
  });

  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    nav?.classList.remove('open');
    toggle?.setAttribute('aria-expanded', 'false');
  });

  const sections = [...document.querySelectorAll('main section[id]')];
  if ('IntersectionObserver' in window) {
    const sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((link) => {
          link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`);
        });
      });
    }, { rootMargin: '-30% 0px -62% 0px' });
    sections.forEach((section) => sectionObserver.observe(section));
  }

  const revealTargets = document.querySelectorAll(
    '.section-heading, .narrative-grid, .runtime-layout, .mechanism-notes, .device-matrix, .evidence-foot, .boundary-grid, .agent-section > *, .video-card, .report-section > *'
  );
  if (!reducedMotion && 'IntersectionObserver' in window) {
    revealTargets.forEach((target) => target.classList.add('reveal'));
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -7% 0px' });
    revealTargets.forEach((target) => revealObserver.observe(target));
  }

  const runtimeContent = {
    pages: {
      src: 'assets/moe-router-loop.png',
      alt: 'MoE Router 跨层专家预测与页缓存预取闭环',
      caption: '页建议随 Prefill、Decode 和设备存储链路切换；专家事实返回后再完成精确结算。'
    },
    experts: {
      src: 'assets/moe-router-loop.png',
      alt: '专家预测、事实结算与错误页回收闭环',
      caption: '预测只提出候选；Router 事实负责结算；错误页回收与驻留更新在有限预算内完成。'
    },
    pressure: {
      src: 'assets/moe-router-loop.png',
      alt: '内存压力约束下的专家页管理闭环',
      caption: 'cgroup headroom、热度和 waste EWMA 共同限制建议量，压力信息不会绕过正确性路径。'
    },
    kv: {
      src: 'assets/kv-eviction.png',
      alt: 'Attention sink、驱逐区和滑动窗口构成的 KV cache 管理',
      caption: 'Attention sink 与 recent window 保留必要上下文，驱逐区按预算释放或换出。'
    }
  };

  const runtimeTabs = [...document.querySelectorAll('[data-runtime-tab]')];
  const runtimePanel = document.querySelector('[data-runtime-panel]');
  const runtimeImage = runtimePanel?.querySelector('img');
  const runtimeCaption = runtimePanel?.querySelector('figcaption');
  runtimeTabs.forEach((tab) => {
    tab.setAttribute('role', 'button');
    tab.setAttribute('tabindex', '0');
    const activate = () => {
      const content = runtimeContent[tab.dataset.runtimeTab];
      if (!content || !runtimeImage || !runtimeCaption) return;
      runtimeTabs.forEach((item) => item.classList.toggle('active', item === tab));
      runtimeImage.src = content.src;
      runtimeImage.alt = content.alt;
      runtimeCaption.textContent = content.caption;
    };
    tab.addEventListener('click', activate);
    tab.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activate();
      }
    });
  });
})();
