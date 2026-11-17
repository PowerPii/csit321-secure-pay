const svg = { width: 24, height: 24, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, "aria-hidden": true } as const;
export const LockIcon = () => <svg {...svg} width={14} height={14}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>;
export const CheckIcon = () => <svg {...svg} width={56} height={56} className="big-icon"><circle cx="12" cy="12" r="10" /><path d="m8 12 3 3 5-6" /></svg>;
export const CrossIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="m9 9 6 6m0-6-6 6" /></svg>;
export const WarnIcon = () => <svg {...svg}><path d="M12 3 2 21h20L12 3z" /><path d="M12 10v5m0 3v.01" /></svg>;
export const ClockIcon = () => <svg {...svg}><circle cx="12" cy="12" r="10" /><path d="M12 7v5l3 2" /></svg>;
