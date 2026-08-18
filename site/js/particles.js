(() => {
  const canvas = document.getElementById('particle-field');
  if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const context = canvas.getContext('2d', { alpha: true });
  if (!context) return;

  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0, active: false };
  let width = 0;
  let height = 0;
  let ratio = 1;
  let particles = [];
  let frame = 0;
  let previous = performance.now();
  let running = true;

  class Particle {
    constructor(index) {
      this.index = index;
      this.reset(true);
    }

    reset(initial = false) {
      this.x = Math.random() * width;
      this.y = initial ? Math.random() * height : height + 18;
      this.vx = (Math.random() - 0.5) * 0.08;
      this.vy = -0.035 - Math.random() * 0.055;
      this.phase = Math.random() * Math.PI * 2;
      this.alpha = 0.14 + Math.random() * 0.28;
      this.size = 0.7 + Math.random() * 1.15;
      this.hue = this.index % 7 === 0 ? '124,114,232' : this.index % 3 === 0 ? '39,215,223' : '79,134,246';
    }

    update(delta, time) {
      const wave = Math.sin(time * 0.00022 + this.phase) * 0.0009;
      this.vx += wave * delta;

      if (pointer.active) {
        const dx = pointer.x - this.x;
        const dy = pointer.y - this.y;
        const distanceSquared = dx * dx + dy * dy;
        if (distanceSquared < 92000 && distanceSquared > 180) {
          const distance = Math.sqrt(distanceSquared);
          const force = (1 - distance / 304) * 0.00032 * delta;
          this.vx += dx * force;
          this.vy += dy * force;
          if (distance < 48) {
            this.vx -= dx * 0.0009 * delta;
            this.vy -= dy * 0.0009 * delta;
          }
        }
      }

      this.vx *= Math.pow(0.987, delta);
      this.vy *= Math.pow(0.992, delta);
      const speed = Math.hypot(this.vx, this.vy);
      if (speed > 0.62) {
        this.vx = (this.vx / speed) * 0.62;
        this.vy = (this.vy / speed) * 0.62;
      }

      this.x += this.vx * delta;
      this.y += this.vy * delta;
      if (this.x < -24) this.x = width + 24;
      if (this.x > width + 24) this.x = -24;
      if (this.y < -30) this.reset(false);
    }

    draw() {
      context.fillStyle = `rgba(${this.hue},${this.alpha})`;
      context.fillRect(this.x, this.y, this.size, this.size);
    }
  }

  const resize = () => {
    width = window.innerWidth;
    height = window.innerHeight;
    ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const count = width < 760 ? 24 : Math.min(52, Math.max(34, Math.round((width * height) / 30000)));
    particles = Array.from({ length: count }, (_, index) => new Particle(index));
  };

  const drawConnections = () => {
    for (let left = 0; left < particles.length; left += 1) {
      for (let right = left + 1; right < particles.length; right += 1) {
        const a = particles[left];
        const b = particles[right];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distanceSquared = dx * dx + dy * dy;
        if (distanceSquared > 13500) continue;
        const nearPointer = pointer.active && (
          (a.x - pointer.x) ** 2 + (a.y - pointer.y) ** 2 < 86000 ||
          (b.x - pointer.x) ** 2 + (b.y - pointer.y) ** 2 < 86000
        );
        if (!nearPointer && (left + right + frame) % 4 !== 0) continue;
        const opacity = (1 - Math.sqrt(distanceSquared) / 116) * (nearPointer ? 0.12 : 0.035);
        context.strokeStyle = `rgba(65,135,226,${opacity})`;
        context.lineWidth = 0.5;
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();
      }
    }
  };

  const animate = (now) => {
    if (!running) return;
    const delta = Math.min((now - previous) / 16.67, 2);
    previous = now;
    pointer.x += (pointer.targetX - pointer.x) * 0.09;
    pointer.y += (pointer.targetY - pointer.y) * 0.09;
    context.clearRect(0, 0, width, height);
    particles.forEach((particle) => {
      particle.update(delta, now);
      particle.draw();
    });
    drawConnections();
    frame += 1;
    requestAnimationFrame(animate);
  };

  window.addEventListener('pointermove', (event) => {
    pointer.targetX = event.clientX;
    pointer.targetY = event.clientY;
    if (!pointer.active) {
      pointer.x = pointer.targetX;
      pointer.y = pointer.targetY;
    }
    pointer.active = true;
  }, { passive: true });

  document.documentElement.addEventListener('pointerleave', () => {
    pointer.active = false;
  });

  document.addEventListener('visibilitychange', () => {
    running = !document.hidden;
    if (running) {
      previous = performance.now();
      requestAnimationFrame(animate);
    }
  });

  window.addEventListener('resize', resize, { passive: true });
  resize();
  requestAnimationFrame(animate);
})();
