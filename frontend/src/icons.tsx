// Inline stroke icons matching the approved mockup's `.ic` style
// (stroke: currentColor, no fill) — never emoji per the mockup's craft rules.

export function CheckIcon({ className = "ic sm" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

export function XIcon({ className = "ic sm" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function WarnIcon({ className = "ic" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.5l9.5 16.5H2.5z" />
      <path d="M12 9.5v5M12 17.5h.01" />
    </svg>
  );
}

export function InfoIcon({ className = "ic" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 10.5v6M12 7.5h.01" />
    </svg>
  );
}

export function FolderIcon({ className = "ic" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 6a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
    </svg>
  );
}

export function TrashIcon({ className = "ic" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 7h14M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-8 0v12a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V7" />
    </svg>
  );
}
