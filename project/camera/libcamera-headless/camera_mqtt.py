#!/usr/bin/env python3
"""Home Assistant discovery and acknowledged controls; never restores ON at boot."""
import json
from pathlib import Path
import queue
import time

RESOLUTIONS = {'12 MP': 1, '5,4 MP': 1.5, '3 MP': 2, '1,3 MP': 3, '0,75 MP': 4, '0,33 MP': 6}
NUMBERS = {
    'focus': ('Ostření', 0, 1023, 1, 'mdi:camera-iris'),
    'quality': ('Kvalita JPEG', 10, 95, 1, 'mdi:image'),
    'fps': ('Cílové FPS', 10, 30, 1, 'mdi:play-speed'),
    'gamma': ('Gama', .5, 4, .05, 'mdi:brightness-6'),
    'contrast': ('Kontrast', .5, 1.8, .02, 'mdi:contrast'),
    'saturation': ('Sytost', 0, 2, .02, 'mdi:palette'),
    'exposure_us': ('Expoziční čas (µs)', 100, 100000, 100, 'mdi:camera-timer'),
    'analogue_gain': ('Analogové zesílení', 1, 8, .1, 'mdi:brightness-6'),
    'zoom': ('Digitální zoom', 1, 10, .1, 'mdi:magnify-plus'),
}


def discovery(config):
    base = config['topic']
    uid = config['device_id']
    device = dict(identifiers=[uid], name='Platina kamera', manufacturer='Xiaomi',
                  model='Mi 8 Lite / IMX363', sw_version='Platina Linux 0.8.1',
                  configuration_url=config['web_url'])
    common = dict(device=device, availability_topic=base + '/availability',
                  state_topic=base + '/state', origin=dict(name='Platina Linux', sw_version='0.8.1',
                  support_url='https://github.com/Sukecz/platina-linux'))
    entities = []

    def add(domain, key, **fields):
        payload = dict(common, unique_id=uid + '_' + key, **fields)
        entities.append((f'homeassistant/{domain}/{uid}/{key}/config', payload))

    add('switch', 'stream', name='Kamera', icon='mdi:video',
        command_topic=base + '/set/enabled', value_template="{{ 'ON' if value_json.enabled else 'OFF' }}",
        payload_on='ON', payload_off='OFF', optimistic=False, retain=False, qos=1)
    for key, (name, low, high, step, icon) in NUMBERS.items():
        add('number', key, name=name, min=low, max=high, step=step, mode='slider', icon=icon,
            command_topic=base + '/set/' + key, value_template='{{ value_json.settings.' + key + ' }}',
            optimistic=False, retain=False, qos=1)
    add('switch', 'white_balance', name='Automatické vyvážení bílé', icon='mdi:white-balance-auto',
        command_topic=base + '/set/automatic',
        value_template="{{ 'ON' if value_json.settings.automatic else 'OFF' }}",
        payload_on='ON', payload_off='OFF', optimistic=False, retain=False, qos=1)
    add('switch', 'exposure_auto', name='Automatická expozice', icon='mdi:camera-auto',
        command_topic=base + '/set/exposure_auto',
        value_template="{{ 'ON' if value_json.settings.exposure_auto else 'OFF' }}",
        payload_on='ON', payload_off='OFF', optimistic=False, retain=False, qos=1)
    for key, name, unit in (('exposure_us_actual', 'Skutečný expoziční čas', 'µs'),
                            ('analogue_gain_actual', 'Skutečné analogové zesílení', '×')):
        add('sensor', key, name=name, unit_of_measurement=unit, state_class='measurement',
            availability=[dict(topic=base + '/availability'),
                          dict(topic=base + '/state', value_template="{{ 'online' if value_json.state == 'on' and value_json." + key + " is number else 'offline' }}")],
            availability_mode='all', value_template='{{ value_json.' + key + ' | default(none) }}')
        entities[-1][1].pop('availability_topic', None)
    choices = json.dumps({str(v): k for k, v in RESOLUTIONS.items()}, ensure_ascii=False)
    add('select', 'resolution', name='Rozlišení', icon='mdi:aspect-ratio', options=list(RESOLUTIONS),
        command_topic=base + '/set/resolution',
        value_template='{{ (' + choices + ')[value_json.settings.scale | string] }}',
        optimistic=False, retain=False, qos=1)
    add('sensor', 'status', name='Stav kamery', icon='mdi:video-check', value_template='{{ value_json.state }}')
    add('sensor', 'fps', name='Skutečné FPS', icon='mdi:play-speed',
        value_template='{{ value_json.fps | default(0) | round(1) }}', state_class='measurement')
    add('button', 'save', name='Uložit nastavení', icon='mdi:content-save',
        command_topic=base + '/set/save', payload_press='PRESS', retain=False, qos=1)
    # Buttons do not consume a state topic.
    entities[-1][1].pop('state_topic', None)
    return entities


class Bridge:
    def __init__(self, camera, path):
        import paho.mqtt.client as mqtt
        self.camera = camera
        self.config = json.loads(Path(path).read_text())
        self.topic = self.config['topic']
        self.commands = queue.Queue(maxsize=16)
        self.connected = False
        self.last_state = None
        self.last_publish = 0
        self.refresh = False
        if hasattr(mqtt, 'CallbackAPIVersion'):
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                      client_id=self.config['device_id'] + '_camera')
        else:
            self.client = mqtt.Client(client_id=self.config['device_id'] + '_camera')
        self.client.username_pw_set(self.config['username'], self.config['password'])
        self.client.will_set(self.topic + '/availability', 'offline', qos=1, retain=True)
        self.client.reconnect_delay_set(1, 30)
        self.client.max_queued_messages_set(64)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def start(self):
        self.client.connect_async(self.config['host'], self.config.get('port', 1883), 30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = reason == 0
        if self.connected:
            client.subscribe([(self.topic + '/set/+', 1), ('homeassistant/status', 1)])
            self.publish_discovery()
            client.publish(self.topic + '/availability', 'online', qos=1, retain=True)
            self.refresh = True

    def on_disconnect(self, client, userdata, *args):
        self.connected = False

    def publish_discovery(self):
        for topic, payload in discovery(self.config):
            self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=True)

    def on_message(self, client, userdata, message):
        if message.topic == 'homeassistant/status':
            if message.payload == b'online':
                self.publish_discovery()
                self.refresh = True
            return
        # Retained commands must never turn the sensor on after startup/reconnect.
        if message.retain or len(message.payload) > 128:
            return
        try:
            self.commands.put_nowait((message.topic.rsplit('/', 1)[-1], message.payload.decode('utf-8')))
        except (queue.Full, UnicodeError):
            pass

    def command(self, key, payload):
        if key in ('enabled', 'automatic', 'exposure_auto'):
            if payload not in ('ON', 'OFF'):
                raise ValueError('Invalid switch command')
            if key == 'enabled':
                self.camera.set_enabled(payload == 'ON')
            else:
                self.camera.configure({key: payload == 'ON'}, save=True)
        elif key == 'resolution':
            self.camera.configure({'scale': RESOLUTIONS[payload]}, save=True)
        elif key in NUMBERS:
            value = float(payload)
            if key in ('focus', 'quality', 'fps', 'exposure_us'):
                if not value.is_integer():
                    raise ValueError('Expected integer')
                value = int(value)
            self.camera.configure({key: value}, save=True)
        elif key == 'save' and payload == 'PRESS':
            self.camera.configure({}, save=True)
        else:
            raise ValueError('Unknown command')

    def tick(self):
        try:
            key, payload = self.commands.get_nowait()
            try:
                self.command(key, payload)
            except (ValueError, KeyError, OSError):
                print('Camera MQTT command rejected', flush=True)
            self.refresh = True
        except queue.Empty:
            pass
        if not self.connected:
            return
        now = time.monotonic()
        # Read image metadata at most once a second, even with no commands.
        if not self.refresh and now - self.last_publish < 1:
            return
        state = json.dumps(self.camera.status(), sort_keys=True)
        if self.refresh or state != self.last_state or now - self.last_publish >= 5:
            self.client.publish(self.topic + '/state', state, qos=1, retain=True)
            self.last_state = state
        self.last_publish = now
        self.refresh = False

    def close(self):
        if self.connected:
            self.client.publish(self.topic + '/state', json.dumps(self.camera.status()), qos=1, retain=True)
            pending = self.client.publish(self.topic + '/availability', 'offline', qos=1, retain=True)
            pending.wait_for_publish(timeout=2)
        self.client.disconnect()
        self.client.loop_stop()
