(() => {
  const canvas = document.getElementById('hero-reactor');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const context = canvas.getContext('2d', { alpha: true });
  const shell = canvas.closest('.hero-reactor');
  const counter = shell?.querySelector('[data-reactor-count]');
  if (!context || !shell) return;

  let width = 0;
  let height = 0;
  let ratio = 1;
  let particles = [];
  let pulses = [];
  let lastPulse = 0;
  let lastCount = 0;
  const pointer = { x: 0, y: 0, tx: 0, ty: 0, active: false };

  const nodes = [
    { x: 0.19, y: 0.28, r: 17, role: 'router' },
    { x: 0.52, y: 0.18, r: 8, role: 'expert' },
    { x: 0.69, y: 0.31, r: 11, role: 'expert' },
    { x: 0.45, y: 0.52, r: 10, role: 'expert' },
    { x: 0.78, y: 0.58, r: 8, role: 'expert' },
    { x: 0.59, y: 0.77, r: 12, role: 'expert' },
    { x: 0.25, y: 0.73, r: 7, role: 'expert' },
  ];

  class PageParticle {
    constructor(index) {
      this.index = index;
      this.reset(Math.random());
    }

    reset(progress = 0) {
      this.progress = progress;
      this.speed = 0.000045 + Math.random() * 0.000055;
      this.lane = Math.floor(Math.random() * 4);
      this.phase = Math.random() * Math.PI * 2;
      this.size = 1.2 + Math.random() * 2.4;
    }

    position(time) {
      const t = this.progress;
      const startX = width * 0.03;
      const startY = height * (0.45 + this.lane * 0.075);
      const routerX = width * nodes[0].x;
      const routerY = height * nodes[0].y;
      if (t < 0.44) {
        const local = t / 0.44;
        return {
          x: startX + (routerX - startX) * local,
          y: startY + (routerY - startY) * local + Math.sin(local * Math.PI + this.phase) * 18,
        };
      }
      const target = nodes[1 + (this.index % (nodes.length - 1))];
      const local = (t - 0.44) / 0.56;
      const bend = Math.sin(local * Math.PI) * (this.index % 2 ? 70 : -70);
      return {
        x: routerX + (width * target.x - routerX) * local + bend * 0.24,
        y: routerY + (height * target.y - routerY) * local + bend,
      };
    }

    update(delta) {
      this.progress += this.speed * delta;
      if (this.progress > 1) this.reset(0);
    }

    draw(time) {
      const position = this.position(time);
      const glow = 0.55 + Math.sin(time * 0.004 + this.phase) * 0.22;
      context.shadowBlur = 14;
      context.shadowColor = 'rgba(38, 219, 230, .75)';
      context.fillStyle = `rgba(112, 231, 239, ${glow})`;
      context.fillRect(position.x - this.size / 2, position.y - this.size / 2, this.size, this.size);
      context.shadowBlur = 0;
    }
  }

  const resize = () => {
    const bounds = shell.getBoundingClientRect();
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    particles = Array.from({ length: width < 600 ? 22 : 46 }, (_, index) => new PageParticle(index));
  };

  const drawGrid = (time) => {
    const drift = (time * 0.012) % 48;
    context.lineWidth = 0.55;
    for (let x = -48 + drift; x < width + 48; x += 48) {
      context.strokeStyle = 'rgba(80, 145, 218, .09)';
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x - width * 0.13, height);
      context.stroke();
    }
    for (let y = 0; y < height; y += 48) {
      context.strokeStyle = 'rgba(80, 145, 218, .075)';
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }
  };

  const drawConnections = (time) => {
    const router = nodes[0];
    nodes.slice(1).forEach((node, index) => {
      const sx = width * router.x;
      const sy = height * router.y;
      const ex = width * node.x;
      const ey = height * node.y;
      const gradient = context.createLinearGradient(sx, sy, ex, ey);
      gradient.addColorStop(0, 'rgba(42, 221, 230, .32)');
      gradient.addColorStop(1, `rgba(75, 125, 241, ${0.06 + (Math.sin(time * 0.002 + index) + 1) * 0.05})`);
      context.strokeStyle = gradient;
      context.lineWidth = index % 2 ? 0.8 : 1.15;
      context.beginPath();
      context.moveTo(sx, sy);
      const curve = index % 2 ? -height * 0.12 : height * 0.12;
      context.quadraticCurveTo((sx + ex) / 2, (sy + ey) / 2 + curve, ex, ey);
      context.stroke();
    });
  };

  const drawNodes = (time) => {
    nodes.forEach((node, index) => {
      let x = width * node.x;
      let y = height * node.y;
      if (pointer.active) {
        const dx = pointer.x - x;
        const dy = pointer.y - y;
        const distance = Math.max(80, Math.hypot(dx, dy));
        if (distance < 260) {
          x -= (dx / distance) * (260 - distance) * 0.06;
          y -= (dy / distance) * (260 - distance) * 0.06;
        }
      }
      const pulse = (Math.sin(time * 0.0025 + index * 1.3) + 1) / 2;
      context.beginPath();
      context.arc(x, y, node.r + 10 + pulse * 12, 0, Math.PI * 2);
      context.strokeStyle = `rgba(57, 198, 225, ${0.07 + pulse * 0.08})`;
      context.lineWidth = 1;
      context.stroke();
      context.beginPath();
      context.arc(x, y, node.r, 0, Math.PI * 2);
      context.fillStyle = node.role === 'router' ? 'rgba(11, 36, 61, .96)' : 'rgba(10, 22, 40, .9)';
      context.fill();
      context.strokeStyle = node.role === 'router' ? 'rgba(82, 231, 235, .9)' : 'rgba(86, 139, 246, .66)';
      context.lineWidth = node.role === 'router' ? 2 : 1;
      context.stroke();
      context.fillStyle = node.role === 'router' ? '#a3fbff' : '#72a5ff';
      context.fillRect(x - 1.3, y - 1.3, 2.6, 2.6);
    });
  };

  const spawnPulse = (time) => {
    if (time - lastPulse < 920) return;
    lastPulse = time;
    pulses.push({ born: time, x: width * nodes[0].x, y: height * nodes[0].y });
    if (counter && time - lastCount > 1800) {
      lastCount = time;
      const active = 2 + Math.floor(Math.random() * 3);
      counter.textContent = `${String(active).padStart(2, '0')} / 512`;
    }
  };

  const drawPulses = (time) => {
    pulses = pulses.filter((pulse) => time - pulse.born < 1600);
    pulses.forEach((pulse) => {
      const progress = (time - pulse.born) / 1600;
      context.beginPath();
      context.arc(pulse.x, pulse.y, 28 + progress * 180, 0, Math.PI * 2);
      context.strokeStyle = `rgba(52, 213, 225, ${0.25 * (1 - progress)})`;
      context.lineWidth = 1;
      context.stroke();
    });
  };

  const drawPointerField = () => {
    if (!pointer.active) return;
    pointer.x += (pointer.tx - pointer.x) * 0.11;
    pointer.y += (pointer.ty - pointer.y) * 0.11;
    const halo = context.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 180);
    halo.addColorStop(0, 'rgba(55, 216, 231, .16)');
    halo.addColorStop(0.3, 'rgba(56, 122, 238, .08)');
    halo.addColorStop(1, 'rgba(4, 8, 14, 0)');
    context.fillStyle = halo;
    context.fillRect(pointer.x - 180, pointer.y - 180, 360, 360);
  };

  const animate = (time) => {
    context.clearRect(0, 0, width, height);
    drawGrid(time);
    drawPointerField();
    drawConnections(time);
    particles.forEach((particle) => {
      particle.update(16.67);
      particle.draw(time);
    });
    drawNodes(time);
    spawnPulse(time);
    drawPulses(time);
    requestAnimationFrame(animate);
  };

  shell.addEventListener('pointermove', (event) => {
    const bounds = shell.getBoundingClientRect();
    pointer.tx = event.clientX - bounds.left;
    pointer.ty = event.clientY - bounds.top;
    if (!pointer.active) {
      pointer.x = pointer.tx;
      pointer.y = pointer.ty;
    }
    pointer.active = true;
  }, { passive: true });
  shell.addEventListener('pointerleave', () => { pointer.active = false; });
  window.addEventListener('resize', resize, { passive: true });
  resize();
  requestAnimationFrame(animate);
})();
