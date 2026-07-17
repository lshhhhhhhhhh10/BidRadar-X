"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useId, useRef, useState } from "react";

type BubblePosition = { left: number; top: number };

export function InfoTip({ text, label = "查看说明" }: { text: string; label?: string }) {
  const tooltipId = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const timerRef = useRef<number | null>(null);
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<BubblePosition>({ left: 14, top: 14 });

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const placeBubble = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const bubbleWidth = bubbleRef.current?.offsetWidth ?? Math.min(280, window.innerWidth - 28);
    const bubbleHeight = bubbleRef.current?.offsetHeight ?? 92;
    const gap = 10;
    const margin = 14;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2 - bubbleWidth / 2, margin),
      window.innerWidth - bubbleWidth - margin,
    );
    const fitsBelow = rect.bottom + gap + bubbleHeight <= window.innerHeight - margin;
    const top = fitsBelow ? rect.bottom + gap : Math.max(margin, rect.top - gap - bubbleHeight);
    setPosition({ left, top });
  }, []);

  const scheduleOpen = useCallback((delay: number) => {
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      setVisible(true);
      timerRef.current = null;
    }, delay);
  }, [clearTimer]);

  const close = useCallback(() => {
    clearTimer();
    setVisible(false);
  }, [clearTimer]);

  useEffect(() => {
    if (!visible) return;
    placeBubble();
    const frame = window.requestAnimationFrame(placeBubble);
    window.addEventListener("resize", placeBubble);
    window.addEventListener("scroll", placeBubble, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", placeBubble);
      window.removeEventListener("scroll", placeBubble, true);
    };
  }, [placeBubble, visible]);

  useEffect(() => () => clearTimer(), [clearTimer]);

  return (
    <>
      <span
        ref={triggerRef}
        className="info-tip"
        tabIndex={0}
        aria-label={label}
        aria-describedby={visible ? tooltipId : undefined}
        onPointerEnter={() => scheduleOpen(2000)}
        onPointerLeave={close}
        onFocus={() => scheduleOpen(150)}
        onBlur={close}
      >
        <span aria-hidden="true">i</span>
      </span>
      {visible && createPortal(
        <span
          ref={bubbleRef}
          id={tooltipId}
          className="info-tip-bubble is-visible"
          role="tooltip"
          style={position}
        >
          {text}
        </span>,
        document.body,
      )}
    </>
  );
}
