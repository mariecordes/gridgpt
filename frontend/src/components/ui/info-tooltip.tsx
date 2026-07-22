'use client';

import { useState } from 'react';
import { Info } from 'lucide-react';

interface InfoTooltipProps {
  text: string;
  label?: string;
}

/**
 * Small accessible info icon that reveals a short explanation on hover, focus,
 * or tap. Dependency-free (no radix), so it stays light for a single use.
 */
export default function InfoTooltip({ text, label = 'More information' }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className="text-gray-400 transition-colors hover:text-gray-600 focus:text-gray-600 focus:outline-none"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
      >
        <Info className="h-4 w-4" />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-6 z-50 w-64 max-w-[calc(100vw-3rem)] rounded-md bg-gray-900 px-3 py-2 text-xs font-normal leading-relaxed text-white shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}
