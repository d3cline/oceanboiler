"""MIDI routing and asynchronous WAV writing."""
import queue
import threading
import time

class MidiRouter:
    def __init__(self, engine):
        self.engine = engine
        self.mapping = {}  # Deliberately learned; KTMP1's assignments are user-changeable.
        self.channel = 10  # 0 means omni; human numbering
        self.threshold = 1
        self.curve = .75
        self.retrigger_ms = 0
        self.learn = None
        self.learn_source = False
        self.last = {}
        self.log = queue.Queue(maxsize=256)

    def report(self, item):
        try: self.log.put_nowait(item)
        except queue.Full: pass

    def receive(self, msg):
        if msg.type == 'control_change':
            self.report(('cc',msg.channel+1,msg.control,msg.value));return
        if msg.type not in ('note_on','note_off'): return
        self.report(('midi', msg.channel+1, msg.note, msg.velocity, msg.type))
        if msg.type != 'note_on' or msg.velocity == 0: return
        if self.channel and msg.channel+1 != self.channel: return
        if self.learn is not None:
            lane = self.learn
            # Unique assignment: a second lane cannot silently steal an existing note.
            old_lane = self.mapping.get(msg.note)
            if old_lane is not None and old_lane != lane:
                self.report(('collision', msg.note, old_lane)); return
            self.mapping = ({**self.mapping} if self.learn_source else {n:l for n,l in self.mapping.items() if l!=lane}) | {msg.note:lane}
            self.learn = None
            self.report(('learned', msg.note, lane))
        if msg.velocity < self.threshold: return
        lane = self.mapping.get(msg.note)
        if lane is None: return
        now = time.monotonic()
        if (now-self.last.get(msg.note, -100))*1000 < self.retrigger_ms: return
        self.last[msg.note] = now
        velocity = max(1, min(127, round(127*(msg.velocity/127)**self.curve)))
        self.engine.trigger(lane, velocity)


class Recorder:
    def __init__(self, path, sr):
        import soundfile as sf
        self.file = sf.SoundFile(path, 'w', samplerate=sr, channels=2, subtype='PCM_24')
        self.queue = queue.Queue(maxsize=1024)
        self.dropped = 0
        self.error = ''
        self.active = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def push(self, block):
        if not self.active: return
        try: self.queue.put_nowait(block.copy())
        except queue.Full: self.dropped += 1

    def run(self):
        try:
            while True:
                data = self.queue.get()
                if data is None: break
                self.file.write(data)
        except Exception as exc: self.error = str(exc)
        finally: self.file.close()

    def close(self):
        self.active = False
        # Timed puts avoid deadlock if disk write failed and consumer exited.
        while self.thread.is_alive():
            try: self.queue.put(None, timeout=.1); break
            except queue.Full: continue
        self.thread.join(timeout=5)
        if self.thread.is_alive(): self.error = 'Recorder still flushing; check disk performance.'
