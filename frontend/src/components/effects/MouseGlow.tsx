import { useEffect, useRef } from "react";

import {
  getStoredTheme,
  THEME_CHANGED_EVENT,
  type Theme,
} from "@/lib/theme";

type Variant = "purple" | "water";

/** 跟随鼠标的质感光效：
 * - purple：双层径向光团（高光核 + 大范围辉光），分层缓动形成视差，静止后缓慢漂移；
 * - water：间歇扩散的水波涟漪 + 柔和环境光；
 * - 暗色用 screen 叠加，亮色用 multiply 叠加（更贴合纸面质感），自动跟随主题。
 */
export function MouseGlow({ variant = "purple" }: { variant?: Variant }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const variantRef = useRef<Variant>(variant);
  const themeRef = useRef<Theme>(getStoredTheme());
  variantRef.current = variant;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);

    const palettes: Record<
      Variant,
      {
        core: [number, number, number];
        halo: [number, number, number];
        ring: [number, number, number];
      }
    > = {
      purple: {
        core: [139, 118, 255],
        halo: [168, 85, 247],
        ring: [139, 118, 255],
      },
      water: {
        core: [56, 189, 248],
        halo: [59, 130, 246],
        ring: [56, 189, 248],
      },
    };

    const rgba = (
      rgb: [number, number, number],
      alpha: number,
    ): string => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;

    const resize = () => {
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
    };
    resize();

    const target = { x: -1000, y: -1000 };
    const core = { x: -1000, y: -1000 };
    const halo = { x: -1000, y: -1000 };
    let lastMoveAt = 0;
    let raf = 0;
    let idlePhase = 0;

    const rings: Array<{ x: number; y: number; born: number }> = [];
    const spawnRing = (x: number, y: number) => {
      if (rings.length > 14) rings.shift();
      rings.push({ x, y, born: performance.now() });
    };

    const move = (event: PointerEvent) => {
      target.x = event.clientX;
      target.y = event.clientY;
      lastMoveAt = performance.now();
      if (variantRef.current === "water") spawnRing(event.clientX, event.clientY);
    };

    const draw = (now: number) => {
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      const isDark = themeRef.current === "dark";

      // 静止漂移：光标 1.2s 未动后，光团沿缓和的利萨如轨迹游走，保持画面活性
      const idle = now - lastMoveAt > 1200;
      if (idle) {
        idlePhase += 0.0006;
        target.x = width / 2 + Math.cos(idlePhase * 7) * width * 0.28;
        target.y = height / 2 + Math.sin(idlePhase * 11) * height * 0.22;
      }

      // 分层缓动：内核快、辉光慢 → 视差深度
      core.x += (target.x - core.x) * 0.085;
      core.y += (target.y - core.y) * 0.085;
      halo.x += (target.x - halo.x) * 0.032;
      halo.y += (target.y - halo.y) * 0.032;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.globalCompositeOperation = isDark ? "screen" : "multiply";

      const palette = palettes[variantRef.current];
      const dim = isDark ? 1 : 0.85;

      if (variantRef.current === "water") {
        // 环境光（水底透光感）
        const ambient = ctx.createRadialGradient(
          halo.x, halo.y, 0,
          halo.x, halo.y, Math.min(620, width / 2.6),
        );
        ambient.addColorStop(0, rgba(palette.halo, 0.1 * dim));
        ambient.addColorStop(0.5, rgba(palette.halo, 0.05 * dim));
        ambient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = ambient;
        ctx.fillRect(0, 0, width, height);

        // 水波涟漪：自光标处缓慢扩散的圆环，渐隐
        for (const ring of rings) {
          const age = (now - ring.born) / 1000;
          const progress = Math.min(1, age / 1.6);
          const radius = 12 + progress * 240;
          const eased = 1 - Math.pow(1 - progress, 3);
          const alpha = 0.34 * (1 - eased) * dim;
          if (alpha <= 0.004) continue;
          const gradient = ctx.createRadialGradient(
            ring.x, ring.y, Math.max(0, radius - 3),
            ring.x, ring.y, radius,
          );
          gradient.addColorStop(0, "rgba(0,0,0,0)");
          gradient.addColorStop(0.82, rgba(palette.ring, alpha));
          gradient.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.arc(ring.x, ring.y, radius + 2, 0, Math.PI * 2);
          ctx.fill();
        }
        for (let i = rings.length - 1; i >= 0; i -= 1) {
          if (now - rings[i].born > 1700) rings.splice(i, 1);
        }
        // 光标处高光核
        const coreGradient = ctx.createRadialGradient(
          core.x, core.y, 0,
          core.x, core.y, 90,
        );
        coreGradient.addColorStop(0, rgba(palette.core, 0.22 * dim));
        coreGradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = coreGradient;
        ctx.fillRect(0, 0, width, height);
      } else {
        // purple：双层光团
        const coreGradient = ctx.createRadialGradient(
          core.x, core.y, 0,
          core.x, core.y, Math.min(220, width / 5),
        );
        coreGradient.addColorStop(0, rgba(palette.core, 0.16 * dim));
        coreGradient.addColorStop(0.55, rgba(palette.core, 0.07 * dim));
        coreGradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = coreGradient;
        ctx.fillRect(0, 0, width, height);

        const haloGradient = ctx.createRadialGradient(
          halo.x, halo.y, 0,
          halo.x, halo.y, Math.min(560, width / 2.2),
        );
        haloGradient.addColorStop(0, rgba(palette.halo, 0.09 * dim));
        haloGradient.addColorStop(0.45, rgba(palette.halo, 0.045 * dim));
        haloGradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = haloGradient;
        ctx.fillRect(0, 0, width, height);
      }

      raf = requestAnimationFrame(draw);
    };

    const onThemeChange = (event: Event) => {
      themeRef.current = (event as CustomEvent<Theme>).detail;
    };

    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", move);
    window.addEventListener(THEME_CHANGED_EVENT, onThemeChange);
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
      window.removeEventListener(THEME_CHANGED_EVENT, onThemeChange);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0"
    />
  );
}
