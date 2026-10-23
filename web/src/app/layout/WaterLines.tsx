import { useEffect, useRef } from 'react';

interface WaterLinesProps {
  color: string;
  /** Pixels between lines. */
  spacing: number;
  /** How far a line swings, in pixels. */
  amplitude: number;
  speed: number;
  /** 0..1 */
  opacity: number;
  /** Lines lean away from the pointer. */
  followPointer: boolean;
  className?: string;
}

type Ripple = { x: number; y: number; born: number };

/** A pond's surface on a plain 2D canvas (the WebGL React Bits Waves drew a white sheet on this laptop's graphics):
 *  wavy lines drift slowly, lean away from the pointer, and a click sends a ring of swell outwards. Stands still with
 *  reduced motion; pauses when the tab is hidden. */
export function WaterLines({ color, spacing, amplitude, speed, opacity, followPointer, className }: WaterLinesProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const props = useRef({ color, spacing, amplitude, speed, opacity, followPointer });
  useEffect(() => {
    props.current = { color, spacing, amplitude, speed, opacity, followPointer };
  });

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return undefined;
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const pointer = { x: -9999, y: -9999 };
    const ripples: Ripple[] = [];
    let width = 0;
    let height = 0;
    let raf = 0;
    const start = performance.now();

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = (now: number) => {
      const p = props.current;
      const t = ((now - start) / 1000) * p.speed;
      ctx.clearRect(0, 0, width, height);
      ctx.strokeStyle = p.color;
      ctx.lineWidth = 1;
      const rect = canvas.getBoundingClientRect();
      const px = pointer.x - rect.left;
      const py = pointer.y - rect.top;
      for (let i = ripples.length - 1; i >= 0; i--) if (now - ripples[i].born > 3200) ripples.splice(i, 1);

      for (let y0 = -spacingPad(p.amplitude); y0 < height + spacingPad(p.amplitude); y0 += p.spacing) {
        // Lines fade in towards the middle of the band of water and out at its edges
        const band = Math.sin(Math.PI * Math.min(1, Math.max(0, y0 / height)));
        ctx.globalAlpha = p.opacity * (0.35 + 0.65 * band);
        ctx.beginPath();
        for (let x = -20; x <= width + 20; x += 8) {
          let dy = Math.sin(x * 0.006 + t * 0.9 + y0 * 0.018) * p.amplitude * 0.6
            + Math.sin(x * 0.013 - t * 0.6 + y0 * 0.007) * p.amplitude * 0.4;
          if (p.followPointer) {
            const d = Math.hypot(x - px, y0 + dy - py);
            if (d < 200) dy += ((y0 + dy - py) / (d || 1)) * (1 - d / 200) ** 2 * 46;
          }
          for (const r of ripples) {
            const age = (now - r.born) / 1000;
            const d = Math.hypot(x - (r.x - rect.left), y0 - (r.y - rect.top));
            const front = age * 320;
            const near = Math.exp(-(((d - front) / 34) ** 2));
            dy += near * Math.sin((d - front) / 9) * 14 * Math.max(0, 1 - age / 3.2);
          }
          if (x === -20) ctx.moveTo(x, y0 + dy);
          else ctx.lineTo(x, y0 + dy);
        }
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (!still && !document.hidden) raf = requestAnimationFrame(draw);
    };

    const onMove = (e: PointerEvent) => {
      pointer.x = e.clientX;
      pointer.y = e.clientY;
    };
    const onDown = (e: PointerEvent) => ripples.push({ x: e.clientX, y: e.clientY, born: performance.now() });
    const onVisible = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) raf = requestAnimationFrame(draw);
    };
    const observer = new ResizeObserver(() => {
      resize();
      if (still) draw(start);
    });

    resize();
    observer.observe(canvas);
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerdown', onDown, { passive: true });
    document.addEventListener('visibilitychange', onVisible);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onDown);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}

const spacingPad = (amplitude: number) => amplitude * 2;
