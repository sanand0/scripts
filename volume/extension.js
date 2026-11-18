import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import Gvc from 'gi://Gvc';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Button} from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {PopupMenuSection} from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Slider} from 'resource:///org/gnome/shell/ui/slider.js';
import {getMixerControl} from 'resource:///org/gnome/shell/ui/status/volume.js';

const MAX = 2;
const STEP = 0.05;
const GESTURES = `
<node>
  <interface name="net.sanand.Volume">
    <method name="Step">
      <arg name="direction" type="i" direction="in"/>
    </method>
  </interface>
</node>`;

class VolumeControl {
    constructor(control, button, panel, section, kind, name, iconName) {
        this.control = control;
        this.kind = kind;
        this.normal = control.get_vol_max_norm();
        this.iconName = iconName;

        const group = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this.icon = new St.Icon({style_class: 'system-status-icon'});
        this.panelValue = new St.Label({
            y_align: Clutter.ActorAlign.CENTER,
            style: 'min-width: 2.7em; text-align: right;',
        });
        group.add_child(this.icon);
        group.add_child(this.panelValue);
        panel.add_child(group);

        const column = new St.BoxLayout({vertical: true, x_expand: true, style: 'spacing: 6px;'});
        const heading = new St.BoxLayout();
        heading.add_child(new St.Label({text: name, x_expand: true}));
        this.menuValue = new St.Label();
        heading.add_child(this.menuValue);
        column.add_child(heading);
        this.slider = new Slider(0);
        this.slider.maximumValue = MAX;
        this.slider.overdriveStart = 1;
        this.slider.accessible_name = name;
        column.add_child(this.slider);
        section.box.add_child(column);

        this.sliderChanged = this.slider.connect('notify::value',
            () => this.setLevel(this.slider.value));
        control.connectObject(
            'state-changed', () => this.bindStream(),
            `default-${kind}-changed`, () => this.bindStream(), button);
        this.button = button;
        this.bindStream();
    }

    bindStream() {
        const stream = this.control.get_state() === Gvc.MixerControlState.READY
            ? (this.kind === 'sink' ? this.control.get_default_sink() : this.control.get_default_source())
            : null;
        if (stream !== this.stream) {
            this.stream?.disconnectObject(this.button);
            this.stream = stream;
            this.stream?.connectObject(
                'notify::volume', () => this.sync(),
                'notify::is-muted', () => this.sync(), this.button);
        }
        this.sync();
    }

    get level() {
        return (this.stream?.volume ?? 0) / this.normal;
    }

    sync() {
        const percent = this.stream ? `${Math.round(100 * this.level)}%` : '—';
        const muted = this.stream?.is_muted;
        this.icon.icon_name = `${this.iconName}-${muted ? 'muted' : 'high'}-symbolic`;
        this.panelValue.text = percent;
        this.menuValue.text = muted ? `${percent} · Muted` : percent;
        this.slider.reactive = !!this.stream;
        this.slider.can_focus = !!this.stream;
        this.slider.opacity = this.stream ? 255 : 96;
        this.slider.block_signal_handler(this.sliderChanged);
        this.slider.value = this.level;
        this.slider.unblock_signal_handler(this.sliderChanged);
    }

    setLevel(level) {
        if (!this.stream)
            return;
        const volume = Math.round(this.normal * Math.clamp(level, 0, MAX));
        if (volume === this.stream.volume)
            return;
        // Volume and mute are independent, including when raising a muted mic.
        this.stream.volume = volume;
        this.stream.push_volume();
    }
}

export default class VolumeExtension extends Extension {
    enable() {
        this.button = new Button(0.5, 'Speaker and microphone volume');
        const panel = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this.button.add_child(panel);
        const section = new PopupMenuSection();
        section.box.set_style('padding: 10px 12px; spacing: 16px;');
        this.button.menu.addMenuItem(section);
        const mixer = getMixerControl();
        const speaker = new VolumeControl(mixer, this.button, panel, section, 'sink', 'Speaker', 'audio-volume');
        const mic = new VolumeControl(mixer, this.button, panel, section, 'source', 'Microphone', 'microphone-sensitivity');
        Main.panel.addToStatusArea(this.uuid, this.button, 1, 'right');

        this.gestures = Gio.DBusExportedObject.wrapJSObject(GESTURES, {
            Step(direction) {
                if (direction !== 1 && direction !== -1)
                    throw new Error('Direction must be 1 or -1');
                const [, , modifiers] = global.get_pointer();
                const target = modifiers & Clutter.ModifierType.CONTROL_MASK ? mic : speaker;
                target.setLevel(target.level + direction * STEP);
            },
        });
        this.gestures.export(Gio.DBus.session, '/net/sanand/Volume');
    }

    disable() {
        this.gestures?.unexport();
        this.gestures = null;
        this.button?.destroy();
        this.button = null;
    }
}
