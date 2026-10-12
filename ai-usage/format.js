// Kept free of GNOME imports so `node --test` can exercise it.
export function countdown(unixSeconds, nowSeconds = Date.now() / 1000) {
    if (!Number.isFinite(unixSeconds)) return 'unknown';
    const minutes = Math.ceil((unixSeconds - nowSeconds) / 60);
    if (minutes <= 0) return 'due now';
    if (minutes >= 24 * 60) return `${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
    return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

export function percent(window) {
    return Number.isFinite(window?.used_percent) ? `${Math.round(window.used_percent)}%` : '—';
}

export function windows(snapshot) {
    const w = snapshot?.windows ?? {};
    return `${percent(w['5h'])} | ${percent(w['7d'])}`;
}

// Thresholds deliberately apply independently to quota usage and time left.
export function quotaTone(value) {
    if (!Number.isFinite(value)) return 'muted';
    return value >= 90 ? 'red' : value >= 70 ? 'amber' : 'green';
}

export function resetTone(duration, unixSeconds, nowSeconds = Date.now() / 1000) {
    if (!Number.isFinite(unixSeconds)) return 'muted';
    const hours = (unixSeconds - nowSeconds) / 3600;
    const red = duration === '5h' ? 0.5 : 12;
    const amber = duration === '5h' ? 1 : 24;
    return hours <= red ? 'red' : hours <= amber ? 'amber' : 'green';
}

export function remaining(unixSeconds, nowSeconds = Date.now() / 1000) {
    const value = countdown(unixSeconds, nowSeconds);
    return value === 'unknown' || value === 'due now' || value.includes('d') ? value : `${value} m`;
}
