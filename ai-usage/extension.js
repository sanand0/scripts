import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {percent, remaining, quotaTone, resetTone} from './format.js';

// GJS async wrappers are not automatically installed by GNOME Shell.
Gio._promisify(Gio.Subprocess.prototype, 'communicate_utf8_async');

const PROVIDERS = [
    {key: 'claude', name: 'Claude Code', script: 'ccusage', icon: 'claude.svg'},
    {key: 'codex', name: 'Codex / ChatGPT', script: 'codexusage', icon: 'openai.svg'},
];
const FREQUENCIES = [0, 1, 5, 10, 30, 60];

function localDate(unixSeconds) {
    if (!Number.isFinite(unixSeconds)) return 'unknown';
    const dt = GLib.DateTime.new_from_unix_local(Math.round(unixSeconds));
    const date = dt.format('%a %d %b %I:%M %p').replace(/\b(AM|PM)\b/g, m => m.toLowerCase()).replace(/\b0(\d):/, '$1:');
    const offset = dt.format('%z');
    const zone = offset.slice(-2) === '00' ? offset.slice(0, 3) : `${offset.slice(0, 3)}:${offset.slice(3, 5)}`;
    return `${date} ${zone}`;
}

function icon(path, size = 15) {
    return new St.Icon({
        gicon: new Gio.FileIcon({file: Gio.File.new_for_path(path)}),
        icon_size: size,
        style_class: 'system-status-icon ai-usage-icon',
    });
}

const UsageIndicator = GObject.registerClass(class UsageIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, 'Claude and Codex quota', false);
        this.extension = extension;
        this.settings = extension.getSettings();
        this.snapshots = {claude: null, codex: null};
        this.errors = {};
        this._refreshing = false;
        this._disposed = false;
        this._processes = [];

        const bar = new St.BoxLayout({style_class: 'ai-usage-panel'});
        this._panel = {};
        for (const [index, provider] of PROVIDERS.entries()) {
            if (index) bar.add_child(new St.Label({text: '  ', y_align: Clutter.ActorAlign.CENTER}));
            bar.add_child(icon(GLib.build_filenamev([extension.path, 'icons', provider.icon])));
            const figures = new St.BoxLayout({style_class: 'ai-usage-panel-values'});
            const labels = {};
            for (const duration of ['5h', '7d']) {
                if (duration === '7d') figures.add_child(new St.Label({text: ' | ', y_align: Clutter.ActorAlign.CENTER}));
                labels[duration] = new St.Label({text: '—', y_align: Clutter.ActorAlign.CENTER, style_class: 'ai-usage-figures ai-usage-muted'});
                figures.add_child(labels[duration]);
            }
            bar.add_child(figures);
            this._panel[provider.key] = labels;
        }
        this.add_child(bar);

        this.menu.addMenuItem(new PopupMenu.PopupMenuItem('AI usage  ·  used quota', {reactive: false, can_focus: false}));
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._details = {};
        for (const provider of PROVIDERS) {
            const heading = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
            const contents = new St.BoxLayout({style_class: 'ai-usage-heading'});
            contents.add_child(icon(GLib.build_filenamev([extension.path, 'icons', provider.icon]), 18));
            contents.add_child(new St.Label({text: provider.name, style_class: `ai-usage-provider-title ai-usage-${provider.key}-title`}));
            heading.add_child(contents);
            this.menu.addMenuItem(heading);
            const details = {};
            for (const duration of ['5h', '7d']) {
                // Separate labels let percentage and countdown use independent color thresholds.
                const item = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
                const line = new St.BoxLayout({style_class: 'ai-usage-quota-row'});
                line.add_child(new St.Label({text: `${duration}: `, style_class: 'ai-usage-quota-prefix'}));
                const percentage = new St.Label({text: '—', style_class: 'ai-usage-percent'});
                line.add_child(percentage);
                line.add_child(new St.Label({text: ' - ', style_class: 'ai-usage-separator'}));
                const time = new St.Label({text: 'checking…', style_class: 'ai-usage-reset'});
                line.add_child(time);
                line.add_child(new St.Label({text: ' - ', style_class: 'ai-usage-separator'}));
                const date = new St.Label({text: '', style_class: 'ai-usage-date'});
                line.add_child(date);
                item.add_child(line);
                this.menu.addMenuItem(item);
                details[duration] = {percentage, time, date};
            }
            const status = new PopupMenu.PopupMenuItem('Not checked yet', {reactive: false, can_focus: false});
            status.label.style_class = 'ai-usage-status';
            this.menu.addMenuItem(status);
            details.status = status.label;
            this._details[provider.key] = details;
            if (provider !== PROVIDERS.at(-1)) this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._refresh = new PopupMenu.PopupMenuItem('Refresh now');
        this._refresh.connect('activate', () => this.refresh());
        this.menu.addMenuItem(this._refresh);
        this._frequency = new PopupMenu.PopupSubMenuMenuItem('Auto-refresh');
        this.menu.addMenuItem(this._frequency);
        this._frequencyChoices = [];
        for (const minutes of FREQUENCIES) {
            const title = minutes === 0 ? 'Off' : minutes === 60 ? 'Every hour' : `Every ${minutes} min`;
            const choice = new PopupMenu.PopupMenuItem(title);
            choice.connect('activate', () => this.settings.set_int('refresh-minutes', minutes));
            this._frequency.menu.addMenuItem(choice);
            this._frequencyChoices.push([minutes, choice]);
        }
        this._settingChanged = this.settings.connect('changed::refresh-minutes', () => this._scheduleRefresh());
        this._scheduleRefresh();
        this._tick = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 30, () => {
            this._draw();
            return GLib.SOURCE_CONTINUE;
        });
        this.refresh();
    }

    _scheduleRefresh() {
        if (this._interval) GLib.Source.remove(this._interval);
        this._interval = 0;
        const minutes = this.settings.get_int('refresh-minutes');
        if (!FREQUENCIES.includes(minutes)) {
            this.settings.set_int('refresh-minutes', 5);
            return;
        }
        this._frequency.label.text = `Auto-refresh: ${minutes ? minutes + ' min' : 'off'}`;
        for (const [value, item] of this._frequencyChoices)
            item.setOrnament(value === minutes ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        if (minutes > 0)
            this._interval = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, minutes * 60, () => {
                this.refresh();
                return GLib.SOURCE_CONTINUE;
            });
    }

    async _load(provider) {
        const script = GLib.build_filenamev([GLib.get_home_dir(), 'code', 'scripts', provider.script]);
        let proc = null;
        try {
            proc = Gio.Subprocess.new([script, '--json'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            this._processes.push(proc);
            const [out, err] = await proc.communicate_utf8_async(null, null);
            if (!proc.get_successful()) throw new Error((err || 'Usage command failed').trim().slice(0, 160));
            const data = JSON.parse(out);
            if (data.provider !== provider.key || !data.windows) throw new Error('Unexpected usage output');
            if (!this._disposed) {
                this.snapshots[provider.key] = data;
                delete this.errors[provider.key];
            }
        } catch (error) {
            if (!this._disposed) this.errors[provider.key] = error.message;
        } finally {
            this._processes = this._processes.filter(p => p !== proc);
            if (!this._disposed) this._draw();
        }
    }

    async refresh() {
        if (this._disposed || this._refreshing) return;
        this._refreshing = true;
        this._refresh.label.text = 'Refreshing…';
        try {
            await Promise.all(PROVIDERS.map(provider => this._load(provider)));
        } finally {
            if (this._disposed) return;
            this._refreshing = false;
            this._refresh.label.text = 'Refresh now';
            this._draw();
        }
    }

    _draw() {
        for (const provider of PROVIDERS) {
            const snapshot = this.snapshots[provider.key];
            const status = this.errors[provider.key];
            const details = this._details[provider.key];
            for (const duration of ['5h', '7d']) {
                const w = snapshot?.windows?.[duration];
                const fields = details[duration];
                const used = w?.used_percent;
                fields.percentage.text = percent(w);
                fields.percentage.style_class = `ai-usage-percent ai-usage-${quotaTone(used)}`;
                const rawReset = w?.resets_at;
                const stamp = typeof rawReset === 'number' ? rawReset : (rawReset ? Date.parse(rawReset) / 1000 : NaN);
                const timeTone = resetTone(duration, stamp);
                fields.time.text = Number.isFinite(stamp) ? remaining(stamp) : 'reset unavailable';
                fields.time.style_class = `ai-usage-reset ai-usage-${timeTone}`;
                fields.date.text = Number.isFinite(stamp) ? localDate(stamp) : '';

                // The panel highlights imminent resets, not quota consumption.
                const panel = this._panel[provider.key][duration];
                panel.text = percent(w);
                const panelTone = status || !Number.isFinite(used) ? 'muted' : timeTone;
                panel.style_class = `ai-usage-figures ai-usage-${panelTone}`;
            }
            const updated = snapshot?.checked_at && Date.parse(snapshot.checked_at);
            const age = updated ? Math.max(0, Math.floor((Date.now() - updated) / 60000)) : null;
            details.status.text = status
                ? `${snapshot ? `Last good: ${age} min ago. ` : ''}Error: ${status}`
                : snapshot ? `Updated ${age} min ago` : 'Not yet checked';
        }
    }

    destroy() {
        this._disposed = true;
        if (this._interval) GLib.Source.remove(this._interval);
        if (this._tick) GLib.Source.remove(this._tick);
        if (this._settingChanged) this.settings.disconnect(this._settingChanged);
        for (const p of this._processes) p.force_exit();
        this._processes = [];
        super.destroy();
    }
});

export default class AIUsageExtension extends Extension {
    enable() {
        this._indicator = new UsageIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator, 1, 'right');
    }
    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
