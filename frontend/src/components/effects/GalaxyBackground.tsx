import { useEffect, useRef } from "react";

type BackgroundStar = {
  x: number;
  y: number;
  z: number;
  r: number;
  base: number;
  speed: number;
  phase: number;
  bright: boolean;
};

type ClusterStar = {
  ox: number;
  oy: number;
  z: number;
  r: number;
  base: number;
  speed: number;
  phase: number;
  bright: boolean;
  orbitSpeed: number;
  orbitPhase: number;
  curX: number;
  curY: number;
  velX: number;
  velY: number;
};

type ConstellationPoint = [number, number];

type Constellation = {
  x: number;
  y: number;
  scale: number;
  base: number;
  phase: number;
  special: boolean;
  points: ConstellationPoint[];
};

const ZODIAC_PATTERNS: ConstellationPoint[][] = [
  [
    [0, 0.2],
    [-0.2, -0.1],
    [0.1, -0.15],
    [0.25, 0.05],
  ],
  [
    [-0.25, -0.1],
    [-0.1, 0.2],
    [0.1, 0.15],
    [0.25, -0.15],
    [0.05, -0.1],
  ],
  [
    [-0.2, -0.2],
    [0, 0.1],
    [0.2, -0.2],
    [0.15, 0.15],
    [-0.05, 0.25],
  ],
  [
    [-0.15, -0.2],
    [0.15, -0.2],
    [0.25, 0.05],
    [0, 0.2],
    [-0.25, 0.05],
  ],
  [
    [-0.25, 0.05],
    [-0.1, -0.2],
    [0.15, -0.15],
    [0.25, 0.1],
    [0, 0.2],
    [-0.2, 0.15],
  ],
  [
    [-0.2, 0.2],
    [-0.1, 0],
    [0.1, -0.05],
    [0.25, 0.1],
    [0.2, -0.2],
  ],
  [
    [-0.2, -0.05],
    [0, -0.15],
    [0.2, -0.05],
    [0, -0.05],
    [-0.1, 0.15],
    [0.1, 0.15],
  ],
  [
    [-0.25, 0.05],
    [-0.1, 0.15],
    [0, 0.05],
    [0.1, -0.1],
    [0.25, -0.2],
    [0.2, -0.05],
  ],
  [
    [-0.25, -0.15],
    [-0.1, -0.2],
    [0.1, -0.05],
    [0.25, 0.05],
    [0.05, 0.2],
    [-0.15, 0.1],
  ],
  [
    [-0.2, 0.2],
    [-0.15, 0.05],
    [0, 0.15],
    [0.1, -0.05],
    [0.2, 0.1],
    [0.25, -0.15],
  ],
  [
    [-0.2, -0.2],
    [-0.1, 0.05],
    [0.1, 0.1],
    [0.2, -0.15],
    [0.25, 0.05],
    [-0.05, 0.2],
  ],
  [
    [-0.2, 0.15],
    [-0.1, -0.05],
    [0.05, -0.15],
    [0.15, -0.05],
    [0.25, 0.15],
    [-0.05, 0.1],
  ],
];

function gaussian() {
  return (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;
}

function smooth(value: number) {
  const x = Math.max(0, Math.min(1, value));
  return x * x * (3 - 2 * x);
}

function makeBackgroundStar(bright = false): BackgroundStar {
  return {
    x: Math.random(),
    y: Math.random(),
    z: 0.15 + Math.random() * 0.85,
    r: bright ? 1.2 + Math.random() : 0.25 + Math.random() * 0.8,
    base: bright ? 0.8 + Math.random() * 0.2 : 0.16 + Math.random() * 0.4,
    speed: 0.6 + Math.random() * 1.6,
    phase: Math.random() * Math.PI * 2,
    bright,
  };
}

function makeClusterStar(index: number): ClusterStar {
  const bright = index % 18 === 0 || Math.random() < 0.06;
  return {
    ox: gaussian() * 0.5,
    oy: gaussian() * 0.38,
    z: 0.45 + Math.random() * 0.55,
    r: bright ? 1.6 + Math.random() * 1.2 : 0.5 + Math.random() * 0.9,
    base: bright ? 0.95 + Math.random() * 0.05 : 0.5 + Math.random() * 0.45,
    speed: 0.7 + Math.random() * 1.6,
    phase: Math.random() * Math.PI * 2,
    bright,
    orbitSpeed: 0.12 + Math.random() * 0.32,
    orbitPhase: Math.random() * Math.PI * 2,
    curX: 0,
    curY: 0,
    velX: 0,
    velY: 0,
  };
}

function makeConstellations(width: number, height: number): Constellation[] {
  const minDim = Math.min(width, height);
  const otherSlots = [
    { x: 0.05, y: 0.09, scale: 0.055, base: 0.34 },
    { x: 0.95, y: 0.08, scale: 0.052, base: 0.3 },
    { x: 0.22, y: 0.06, scale: 0.058, base: 0.38 },
    { x: 0.78, y: 0.06, scale: 0.055, base: 0.34 },
    { x: 0.04, y: 0.45, scale: 0.058, base: 0.38 },
    { x: 0.96, y: 0.5, scale: 0.055, base: 0.34 },
    { x: 0.06, y: 0.82, scale: 0.052, base: 0.3 },
    { x: 0.94, y: 0.84, scale: 0.055, base: 0.34 },
    { x: 0.28, y: 0.92, scale: 0.052, base: 0.3 },
    { x: 0.72, y: 0.9, scale: 0.055, base: 0.34 },
  ];

  return ZODIAC_PATTERNS.map((points, index) => {
    const special = index === 6 || index === 9; // Libra, Capricorn
    let x: number;
    let y: number;
    let scale: number;
    let base: number;

    if (special) {
      x = index === 6 ? width * 0.13 : width * 0.87;
      y = index === 6 ? height * 0.17 : height * 0.78;
      scale = minDim * 0.21;
      base = 1;
    } else {
      const slotIndex = index < 6 ? index : index < 9 ? index - 1 : index - 2;
      const slot = otherSlots[slotIndex];
      const jitterX = (Math.random() - 0.5) * 0.05;
      const jitterY = (Math.random() - 0.5) * 0.05;
      x = Math.max(
        width * 0.03,
        Math.min(width * 0.97, width * (slot.x + jitterX)),
      );
      y = Math.max(
        height * 0.04,
        Math.min(height * 0.96, height * (slot.y + jitterY)),
      );
      scale = minDim * slot.scale * (0.85 + Math.random() * 0.3);
      base = slot.base * (0.85 + Math.random() * 0.3);
    }

    return {
      x,
      y,
      scale,
      base,
      phase: Math.random() * Math.PI * 2,
      special,
      points,
    };
  });
}

export function GalaxyBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = 0;
    let height = 0;
    let backgroundStars: BackgroundStar[] = [];
    let clusterStars: ClusterStar[] = [];
    let constellations: Constellation[] = [];
    let raf = 0;
    const mouse = { targetX: 0.5, targetY: 0.5, x: 0.5, y: 0.5 };
    const cluster = { x: 0, y: 0, velX: 0, velY: 0 };
    let prevMouseX = 0;
    let prevMouseY = 0;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const clusterCount = width < 640 ? 380 : width < 1280 ? 760 : 1100;
      const backgroundCount = width < 640 ? 45 : width < 1280 ? 85 : 120;

      cluster.x = width * 0.72;
      cluster.y = height * 0.26;
      cluster.velX = 0;
      cluster.velY = 0;
      prevMouseX = mouse.x * width;
      prevMouseY = mouse.y * height;

      backgroundStars = Array.from({ length: backgroundCount }, (_, i) =>
        makeBackgroundStar(i % 20 === 0),
      );
      clusterStars = Array.from({ length: clusterCount }, (_, i) =>
        makeClusterStar(i),
      );
      constellations = makeConstellations(width, height);
    };

    const move = (event: PointerEvent) => {
      if (width <= 0 || height <= 0) return;
      mouse.targetX = event.clientX / width;
      mouse.targetY = event.clientY / height;
    };

    const drawConstellation = (constellation: Constellation, time: number) => {
      const screenPoints = constellation.points.map(([px, py]) => ({
        x: constellation.x + px * constellation.scale,
        y: constellation.y + py * constellation.scale,
      }));

      if (!constellation.special) {
        const breath = reduced
          ? 1
          : 0.78 + 0.22 * Math.sin(time * 0.00012 + constellation.phase);
        const flicker = reduced
          ? 1
          : 0.9 + 0.1 * Math.sin(time * 0.0002 + constellation.phase * 2.1);
        const lineAlpha = constellation.base * 0.4 * breath;
        const pointAlpha = constellation.base * 0.7 * breath * flicker;

        ctx.strokeStyle = `rgba(255, 255, 255, ${lineAlpha * 0.06})`;
        ctx.lineWidth = 2.6;
        ctx.beginPath();
        screenPoints.forEach((point, index) => {
          if (index === 0) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        });
        ctx.stroke();

        ctx.strokeStyle = `rgba(220, 235, 255, ${lineAlpha})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        screenPoints.forEach((point, index) => {
          if (index === 0) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        });
        ctx.stroke();

        screenPoints.forEach((point) => {
          ctx.globalAlpha = pointAlpha;
          ctx.fillStyle = "#ffffff";
          ctx.beginPath();
          ctx.arc(point.x, point.y, 1, 0, Math.PI * 2);
          ctx.fill();
        });
        return;
      }

      const pointCount = screenPoints.length;
      const segmentCount = Math.max(1, pointCount - 1);
      const cycleDuration = reduced
        ? 0
        : 17000 *
          (0.88 + 0.24 * Math.sin(time * 0.00003 + constellation.phase * 3.1));
      const progress = reduced
        ? 1
        : (time / cycleDuration + constellation.phase) % 1;
      const drawEnd = 0.55;
      const breatheEnd = 0.92;
      const breathe = reduced
        ? 1
        : 0.72 + 0.28 * Math.sin(time * 0.00018 + constellation.phase * 2.7);
      const completion =
        progress < drawEnd
          ? smooth(progress / drawEnd)
          : progress < breatheEnd
            ? 1
            : smooth(1 - (progress - breatheEnd) / (1 - breatheEnd));
      const brightness = completion * breathe;

      const segmentLevel = (index: number) => {
        if (reduced) return 1;
        if (progress < drawEnd) {
          const t = progress / drawEnd;
          return smooth((t * segmentCount - index) / 0.22);
        }
        if (progress < breatheEnd) return 1;
        const t = (progress - breatheEnd) / (1 - breatheEnd);
        return smooth(1 - t);
      };

      const pointLevel = (index: number) => {
        if (reduced) return 1;
        if (progress < drawEnd) {
          const t = progress / drawEnd;
          return smooth((t * Math.max(1, pointCount - 1) - index) / 0.22);
        }
        if (progress < breatheEnd) return 1;
        const t = (progress - breatheEnd) / (1 - breatheEnd);
        return smooth(1 - t);
      };

      for (let index = 0; index < segmentCount; index++) {
        const start = screenPoints[index];
        const end = screenPoints[index + 1];
        const level = segmentLevel(index) * brightness;
        const lineAlpha = level * 0.95;

        ctx.strokeStyle = `rgba(255, 255, 255, ${lineAlpha * 0.08})`;
        ctx.lineWidth = 4.4;
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();

        ctx.strokeStyle = `rgba(235, 244, 255, ${lineAlpha})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();
      }

      screenPoints.forEach((point, index) => {
        const level = pointLevel(index) * brightness;
        const radius = 2.6;
        ctx.globalAlpha = level;
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fill();

        ctx.globalAlpha = level * 0.1;
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius * 1.8, 0, Math.PI * 2);
        ctx.fill();
      });
    };

    const draw = (time: number) => {
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;
      ctx.clearRect(0, 0, width, height);

      const minDim = Math.min(width, height);
      const mouseDx = mouse.x - 0.5;
      const mouseDy = mouse.y - 0.5;

      const targetX = Math.max(
        width * 0.15,
        Math.min(
          width * 0.88,
          width * 0.72 + mouseDx * Math.min(280, width * 0.2),
        ),
      );
      const targetY = Math.max(
        height * 0.04,
        Math.min(
          height * 0.76,
          height * 0.26 + mouseDy * Math.min(220, height * 0.2),
        ),
      );
      cluster.velX += (targetX - cluster.x) * 0.055;
      cluster.velX *= 0.86;
      cluster.velY += (targetY - cluster.y) * 0.055;
      cluster.velY *= 0.86;
      cluster.x += cluster.velX;
      cluster.y += cluster.velY;

      const clusterX = cluster.x;
      const clusterY = cluster.y;

      const rotation = reduced ? 0 : time * 0.00005;
      const cos = Math.cos(rotation);
      const sin = Math.sin(rotation);

      const mouseX = mouse.x * width;
      const mouseY = mouse.y * height;
      const mouseVelX = mouseX - prevMouseX;
      const mouseVelY = mouseY - prevMouseY;
      prevMouseX = mouseX;
      prevMouseY = mouseY;

      for (const star of clusterStars) {
        const rotatedX = star.ox * cos - star.oy * sin;
        const rotatedY = star.ox * sin + star.oy * cos;
        const driftX = reduced
          ? 0
          : Math.sin(time * 0.00025 * star.orbitSpeed + star.orbitPhase) *
            minDim *
            0.015 *
            star.z;
        const driftY = reduced
          ? 0
          : Math.cos(time * 0.00025 * star.orbitSpeed + star.orbitPhase) *
            minDim *
            0.012 *
            star.z;
        const baseX = clusterX + rotatedX * minDim * star.z + driftX;
        const baseY = clusterY + rotatedY * minDim * star.z + driftY;

        const deltaX = baseX - mouseX;
        const deltaY = baseY - mouseY;
        const distance = Math.hypot(deltaX, deltaY) || 1;
        const influenceRadius = minDim * 0.36;
        const nearRadius = minDim * 0.14;
        const drag = Math.max(0, 1 - distance / influenceRadius);
        const mouseSpeed = Math.hypot(mouseVelX, mouseVelY);

        let desiredVelX = 0;
        let desiredVelY = 0;

        if (mouseSpeed > 0.2) {
          const flow = drag * drag * (0.8 + 1.6 * star.z);
          desiredVelX = mouseVelX * flow;
          desiredVelY = mouseVelY * flow;
        }

        if (distance < nearRadius && distance > 0.5) {
          const push = (1 - distance / nearRadius) * (2 + 5 * star.z);
          desiredVelX += (deltaX / distance) * push;
          desiredVelY += (deltaY / distance) * push;
        }

        const response =
          distance < nearRadius
            ? 0.18
            : distance < influenceRadius
              ? 0.07
              : 0.025;
        const returnSpring = 0.0012 + (1 - drag) * 0.001;
        star.velX +=
          (desiredVelX - star.velX) * response - star.curX * returnSpring;
        star.velY +=
          (desiredVelY - star.velY) * response - star.curY * returnSpring;
        star.velX *= 0.82;
        star.velY *= 0.82;
        star.curX += star.velX;
        star.curY += star.velY;

        const jitterX = reduced
          ? 0
          : Math.sin(time * 0.0007 + star.phase) * (0.4 + 0.5 * star.z);
        const jitterY = reduced
          ? 0
          : Math.cos(time * 0.0006 + star.phase * 1.7) * (0.35 + 0.45 * star.z);
        const x = baseX + star.curX + jitterX;
        const y = baseY + star.curY + jitterY;

        const twinkle = reduced
          ? 1
          : 0.72 + 0.28 * Math.sin(time * 0.001 * star.speed + star.phase);
        const alpha = Math.min(1, star.base * twinkle);

        ctx.globalAlpha = alpha;
        ctx.fillStyle = star.bright
          ? "#ffffff"
          : star.z > 0.72
            ? "#f2f8ff"
            : "#dceaff";
        ctx.beginPath();
        ctx.arc(x, y, star.r, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const star of backgroundStars) {
        const parallax = (star.z - 0.15) * 0.7;
        const offsetX = mouseDx * parallax * 90;
        const offsetY = mouseDy * parallax * 55;
        let x = (star.x * width + offsetX) % width;
        let y = (star.y * height + offsetY) % height;
        if (x < 0) x += width;
        if (y < 0) y += height;

        const twinkle = reduced
          ? 1
          : 0.7 + 0.3 * Math.sin(time * 0.001 * star.speed + star.phase);
        ctx.globalAlpha = Math.min(1, star.base * twinkle);
        ctx.fillStyle = star.bright ? "#ffffff" : "#d9e6ff";
        ctx.beginPath();
        ctx.arc(x, y, star.r, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const constellation of constellations) {
        drawConstellation(constellation, time);
      }

      if (!reduced) {
        raf = requestAnimationFrame(draw);
      }
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", move, { passive: true });
    if (reduced) {
      draw(0);
    } else {
      raf = requestAnimationFrame(draw);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
    };
  }, []);

  return (
    <div
      aria-hidden
      className="galaxy-root pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <div className="galaxy-nebula absolute inset-0" />
      <div className="galaxy-vignette absolute inset-0" />
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
