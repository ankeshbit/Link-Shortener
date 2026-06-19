import React, { useRef, useEffect } from "react";
import { motion, useMotionValue, animate } from "motion/react";

export function TextRepel({ text, className = "", style = {} }) {
  const words = text.split(" ");

  return (
    <span className={className} style={{ display: "inline-block", ...style }}>
      {words.map((word, wordIdx) => (
        <span key={wordIdx} style={{ display: "inline-block", whiteSpace: "nowrap" }}>
          {word.split("").map((char, charIdx) => (
            <RepelChar key={charIdx} char={char} />
          ))}
          {/* Add a space after the word, unless it's the last word */}
          {wordIdx < words.length - 1 && <span style={{ display: "inline-block" }}>&nbsp;</span>}
        </span>
      ))}
    </span>
  );
}

function RepelChar({ char }) {
  const charRef = useRef(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!charRef.current) return;

      const rect = charRef.current.getBoundingClientRect();
      // Subtract the current translations to get the original un-translated center coordinates
      const centerX = rect.left + rect.width / 2 - x.get();
      const centerY = rect.top + rect.height / 2 - y.get();

      const mouseX = e.clientX;
      const mouseY = e.clientY;

      const dx = centerX - mouseX;
      const dy = centerY - mouseY;
      const distance = Math.sqrt(dx * dx + dy * dy);

      const radius = 100; // Radius of influence in pixels
      const strength = 18; // Maximum repulsion displacement in pixels

      let targetX = 0;
      let targetY = 0;

      if (distance < radius) {
        // Linear force decay: stronger repulsion close to the cursor
        const force = (radius - distance) / radius;
        const angle = Math.atan2(dy, dx);
        targetX = Math.cos(angle) * force * strength;
        targetY = Math.sin(angle) * force * strength;
      }

      // Performance: do not restart spring animations to 0 if the values are already idle at 0
      if (targetX === 0 && targetY === 0 && x.get() === 0 && y.get() === 0) {
        return;
      }

      // Smoothly animate the motion values with spring physics
      animate(x, targetX, { type: "spring", damping: 15, stiffness: 150 });
      animate(y, targetY, { type: "spring", damping: 15, stiffness: 150 });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [x, y]);

  return (
    <motion.span
      ref={charRef}
      style={{ display: "inline-block", x, y }}
    >
      {char}
    </motion.span>
  );
}
