import { useRef, useEffect } from "react";

export function MagnetLines({
  rows = 9,
  columns = 9,
  containerSize = "80vmin",
  lineColor = "#efefef",
  lineWidth = "1vmin",
  lineHeight = "6vmin",
  baseAngle = 0,
  className = "",
  style = {},
}) {
  const containerRef = useRef(null);
  const lineRefs = useRef([]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) return;

    let rafId = null;
    let mouseX = 0;
    let mouseY = 0;
    let hasMoved = false;

    const onMouseMove = (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      hasMoved = true;
      if (!rafId) {
        rafId = requestAnimationFrame(updateLines);
      }
    };

    const updateLines = () => {
      rafId = null;
      if (!hasMoved || !containerRef.current) return;

      const lines = lineRefs.current;
      for (let i = 0; i < lines.length; i++) {
        const el = lines[i];
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dx = mouseX - centerX;
        const dy = mouseY - centerY;
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        el.style.transform = `rotate(${angle + baseAngle}deg)`;
      }
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [baseAngle]);

  const total = rows * columns;

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        display: "grid",
        placeItems: "center",
        position: "relative",
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gridTemplateRows: `repeat(${rows}, 1fr)`,
        width: containerSize,
        height: containerSize,
        ...style,
      }}
    >
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          ref={(el) => (lineRefs.current[i] = el)}
          style={{
            width: lineWidth,
            height: lineHeight,
            backgroundColor: lineColor,
            borderRadius: "9999px",
            transform: `rotate(${baseAngle}deg)`,
            transition: "transform 0.12s ease-out",
            willChange: "transform",
          }}
        />
      ))}
    </div>
  );
}
