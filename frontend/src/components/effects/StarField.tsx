import { useEffect, useRef } from "react";

/** 微型动态星空：适合嵌在按钮条/卡片内部点缀（闪烁 + 缓慢漂移）。 */
export function StarField({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    interface Star {
      x: number;
      y: number;
      radius: number;
      phase: number;
      speed: number;
      drift: number;
    }
    const stars: Star[] = Array.from({ length: 46 }, () => ({
      x: Math.random(),
      y: Math.random(),
      radius: 0.4 + Math.random() * 1.1,
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.4,
      drift: 0.08 + Math.random() * 0.25,
    }));

    let raf = 0;
    const draw = (now: number) => {
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      for (const star of stars) {
        star.y -= star.drift * 0.0004;
        if (star.y < -0.02) {
          star.y = 1.02;
          star.x = Math.random();
        }
        const twinkle =
          0.35 + 0.65 * (0.5 + 0.5 * Math.sin(now * 0.001 * star.speed + star.phase));
        const x = star.x * width;
        const y = star.y * height;
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, star.radius * 3);
        gradient.addColorStop(0, `rgba(255,255,255,${0.85 * twinkle})`);
        gradient.addColorStop(0.4, `rgba(190,220,255,${0.28 * twinkle})`);
        gradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, star.radius * 3, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} aria-hidden className={className} />;
}
