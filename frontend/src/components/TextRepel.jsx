import { useRef, useEffect } from "react";

export function TextRepel({ text, className = "", style = {} }) {
  const containerRef = useRef(null);
  const charRefs = useRef([]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mediaQuery.matches) return;

    let rafId = null;
    let mouseX = 0;
    let mouseY = 0;

    const onMouseMove = (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      if (!rafId) {
        rafId = requestAnimationFrame(updateRepel);
      }
    };

    const updateRepel = () => {
      rafId = null;
      if (!containerRef.current) return;

      const radius = 90;
      const strength = 16;
      const chars = charRefs.current;

      for (let i = 0; i < chars.length; i++) {
        const el = chars[i];
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;

        const dx = centerX - mouseX;
        const dy = centerY - mouseY;
        const dist = Math.hypot(dx, dy);

        if (dist < radius) {
          const force = (radius - dist) / radius;
          const angle = Math.atan2(dy, dx);
          const tx = Math.cos(angle) * force * strength;
          const ty = Math.sin(angle) * force * strength;
          el.style.transform = `translate(${tx}px, ${ty}px)`;
        } else {
          el.style.transform = "translate(0px, 0px)";
        }
      }
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, []);

  const words = text.split(" ");
  let globalIndex = 0;

  return (
    <span
      ref={containerRef}
      className={className}
      style={{ display: "inline-block", ...style }}
    >
      {words.map((word, wordIdx) => (
        <span
          key={wordIdx}
          style={{ display: "inline-block", whiteSpace: "nowrap" }}
        >
          {word.split("").map((char) => {
            const idx = globalIndex++;
            return (
              <span
                key={idx}
                ref={(el) => (charRefs.current[idx] = el)}
                style={{
                  display: "inline-block",
                  transition: "transform 0.15s ease-out",
                  willChange: "transform",
                }}
              >
                {char}
              </span>
            );
          })}
          {wordIdx < words.length - 1 && (
            <span style={{ display: "inline-block" }}>&nbsp;</span>
          )}
        </span>
      ))}
    </span>
  );
}
