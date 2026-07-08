"use client";

import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

type UseDialogBehaviorOptions = {
  /** Whether the dialog/drawer/lightbox is currently open. */
  open: boolean;
  /** Called on Escape or when the caller should close the overlay. */
  onClose: () => void;
};

/**
 * Shared overlay behavior for modals, drawers, and lightboxes: closes on
 * Escape, traps Tab focus inside the panel, autofocuses the first focusable
 * element on open, restores focus to the trigger on close, and locks body
 * scroll via the `body.modal-open` class already defined in globals.css.
 *
 * Attach the returned `panelRef` to the focus-trapped container element.
 */
export function useDialogBehavior<T extends HTMLElement>({
  open,
  onClose,
}: UseDialogBehaviorOptions) {
  const panelRef = useRef<T | null>(null);
  const triggerRef = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return undefined;

    triggerRef.current = document.activeElement;
    document.body.classList.add("modal-open");

    const panel = panelRef.current;
    const focusable = panel?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    focusable?.[0]?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const nodes = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (!nodes || nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("modal-open");
      const trigger = triggerRef.current;
      if (trigger instanceof HTMLElement) {
        trigger.focus();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return { panelRef };
}
