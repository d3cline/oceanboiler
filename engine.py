"""OCEANBOILER — procedural bass/percussion engine; no sample packs or network calls."""
from dataclasses import dataclass, asdict, replace, field
import math
import queue
import numpy as np
from scipy.signal import lfilter

SR = 48000
KINDS = ['Growl', 'Talking bass', 'Reese', 'Sub drop', 'Kick', 'Snare', 'Hat', 'Metal', 'Rubber wub', 'Scratch', 'Weeewhaa', 'Bubble', 'Neuro', 'Sub sine']
RATES = [0.5, 1, 1.5, 2, 3, 4, 6, 8]

@dataclass
class Patch:
    kind: str = 'Growl'
    note: int = 29
    decay: float = 1.4
    tone: float = 0.5
    motion: float = 0.72
    drive: float = 0.55
    rate: float = 2.0  # LFO cycles per quarter note
    level: float = 0.7
    pan: float = 0.0
    send: float = 0.18
    ratio: float = 2.0
    sweep: float = 12.0
    texture: float = 0.5
    name: str = ""
    layers: list = field(default_factory=list)


def kit(name='Abyss'):
    p = [Patch('Growl', 29, 1.3), Patch('Talking bass', 29, 1.8, .65, .85, .6, 1),
         Patch('Reese', 29, 1.8, .4, .6, .5, .5), Patch('Sub drop', 29, 2.0, .4, .5, .4, 1),
         Patch('Kick', 29, .5, .55, .3, .35, 1, .85, 0, 0),
         Patch('Snare', 50, .32, .55, .4, .4, 1, .7, 0, .12),
         Patch('Hat', 75, .12, .7, .5, .2, 1, .38, .22, .14),
         Patch('Metal', 41, .7, .6, .7, .45, 3, .55, -.2, .32)]
    if name == 'Bog ritual':
        p[0] = Patch('Talking bass', 26, 2.3, .25, .94, .8, 1.5)
        p[1] = Patch('Growl', 26, 1.4, .3, .8, .7, 3)
        p[2] = Patch('Reese', 26, 2.7, .25, .3, .65, .5)
    elif name == 'Chrome teeth':
        p[0] = Patch('Growl', 31, .85, .9, 1, .85, 4)
        p[1] = Patch('Metal', 43, .65, .8, .9, .8, 6)
        p[2] = Patch('Talking bass', 31, 1.5, .8, 1, .75, 3)
    elif name == 'Deep pressure':
        p[0] = Patch('Reese', 24, 2.8, .2, .5, .5, .5)
        p[1] = Patch('Talking bass', 24, 2.0, .2, .8, .5, 1)
        p[3] = Patch('Sub drop', 24, 3, .2, .5, .2, 1)
    return p


def pattern():
    a = [[0] * 32 for _ in range(8)]
    for s in [0, 11, 16, 26]: a[4][s] = 112
    for s in [8, 24]: a[5][s] = 115
    for s in range(0, 32, 2): a[6][s] = 72 if s % 4 else 95
    for s in [0, 6, 16, 22]: a[0][s] = 105
    for s in [12, 28]: a[1][s] = 110
    a[7][30] = 80
    return a


def biquad(mode, hz, q, sr):
    w = 2 * math.pi * min(sr * .43, max(20, hz)) / sr
    c, s = math.cos(w), math.sin(w)
    alpha = s / (2 * q)
    if mode == 'low': b = [(1-c)/2, 1-c, (1-c)/2]
    elif mode == 'high': b = [(1+c)/2, -(1+c), (1+c)/2]
    else: b = [alpha, 0, -alpha]
    a = np.array([1+alpha, -2*c, 1-alpha])
    return np.array(b) / a[0], a / a[0]


class Voice:
    def __init__(self, lane, patch, velocity, sr, seed):
        self.lane, self.p, self.sr = lane, replace(patch), sr
        self.age = 0
        self.velocity = (velocity / 127) ** .7
        self.rng = np.random.default_rng(seed)
        self.z = [np.zeros(2) for _ in range(4)]
        self.kill_left = None
        self.phase = 0.
        if patch.kind == 'Scratch':
            u = np.arange(4096) / 4096
            self.tape = sum(np.sin(2*np.pi*k*u)/k for k in range(1,17))
            self.tape += .25*self.rng.standard_normal(4096)
            self.tape = np.tanh(self.tape*2)


    def choke(self):
        if self.kill_left is None: self.kill_left = int(.015 * self.sr)

    @property
    def done(self):
        return self.age >= int(self.p.decay * self.sr) or self.kill_left == 0

    def filt(self, x, mode, hz, q, i):
        b, a = biquad(mode, hz, q, self.sr)
        out, self.z[i] = lfilter(b, a, x, zi=self.z[i])
        return out

    def render(self, n, bpm, morph, grit):
        p, sr = self.p, self.sr
        t = (self.age + np.arange(n)) / sr
        f = 440 * 2 ** ((p.note - 69) / 12)
        ph = 2 * np.pi * f * t
        wob = .5 - .5 * np.cos(2 * np.pi * t * bpm / 60 * p.rate)
        amount = np.clip(p.motion * morph, 0, 1.5)
        tone = p.tone
        noise = self.rng.standard_normal(n)
        sub = np.sin(ph)
        if p.kind == 'Sub sine':
            x = .85*sub
        elif p.kind in ('Growl', 'Talking bass'):
            index = .8 + (1.8 + 5 * amount) * wob
            fm = np.sin(ph + index * np.sin(ph * (2 if p.kind == 'Growl' else 1.5)))
            fm += .22 * np.sin(ph * 3.003 + 2 * np.sin(ph * .5))
            fm = np.tanh(fm * (1 + 3 * p.drive))
            if p.kind == 'Talking bass':
                vowel = float(wob.mean())
                body = self.filt(fm, 'band', 280 + 750*vowel + 350*tone, 4.5, 0)
                body += .65*self.filt(fm, 'band', 850 + 1550*(1-vowel) + 500*tone, 6, 1)
                body *= 2.1
            else:
                body = self.filt(fm, 'low', 140 + (500 + 4300*tone) * (.08 + float(wob.mean())*amount), 1.1, 0)
            x = .65*body*(.22+.78*wob) + .36*sub
        elif p.kind == 'Reese':
            # Smooth harmonic oscillators: detuned analog-like saw partials, no bit crushing.
            body = np.zeros(n)
            for harmonic in range(1, 13):
                body += (np.sin(ph*harmonic*1.006) + np.sin(ph*harmonic*.994)) / harmonic
            body = self.filt(body, 'low', 180 + 2800*tone*(.2+amount*float(wob.mean())), .85, 0)
            x = .35*np.tanh(body*(1+2*p.drive)) + .4*sub
        elif p.kind == 'Rubber wub':
            body = sum(np.sin(ph*k)/k for k in range(1,17))
            cutoff = 100 * (15+100*tone) ** (.1+.8*float(wob.mean())*min(amount,1))
            x = .6*self.filt(body, 'low', cutoff, .6+2.4*p.texture, 0) + .3*sub
        elif p.kind == 'Scratch':
            # Variable-rate forward/reverse reading of an original procedural tape.
            gesture = np.sin(2*np.pi*t*bpm/60*p.rate)
            position = (f*t*.12 + gesture*(.5+3*p.texture))*4096
            base = np.floor(position).astype(np.int64); frac = position-base
            body = self.tape[base%4096]*(1-frac)+self.tape[(base+1)%4096]*frac
            gate = .18+.82*np.abs(np.cos(2*np.pi*t*bpm/60*p.rate))**(.5+3*amount)
            x = self.filt(body,'band',500+6000*tone,.7+2*p.texture,0)*gate
        elif p.kind in ('Weeewhaa','Bubble'):
            if p.kind == 'Weeewhaa':
                contour = np.sin(np.pi*np.minimum(t/p.decay,1))
            else:
                contour = np.exp(-t/(.025+.15*p.texture))
            freq = f * 2**(p.sweep*contour/12)
            phase = self.phase + 2*np.pi*np.cumsum(freq)/sr
            self.phase = float(phase[-1] % (2*np.pi))
            carrier = np.sin(phase + (.3+4*amount)*np.sin(phase*p.ratio))
            body = self.filt(carrier,'band',250+3500*(1-float(contour.mean()))*(.2+tone),1+3*p.texture,0)
            x = .8*body+.25*np.sin(phase)
        elif p.kind == 'Neuro':
            carrier = np.sin(ph+(1+7*amount*wob)*np.sin(ph*p.ratio+.7*np.sin(ph*.503)))
            moving = self.filt(carrier,'band',150+3800*tone*(.2+float(wob.mean())),2+5*p.texture,0)
            x = .55*np.tanh((carrier-moving*.8)*(1+3*p.drive))+.3*sub
        elif p.kind == 'Sub drop':
            phase = 2*np.pi*f*(t + .11*(1-np.exp(-t*12)))
            x = .82*np.sin(phase) + .15*np.sin(2*phase)*np.exp(-t*4)
        elif p.kind == 'Kick':
            phase = 2*np.pi*(f*t + (90+tone*130)*.025*(1-np.exp(-t/.025)))
            click = self.filt(noise, 'high', 3200, .7, 0)*np.exp(-t*250)
            x = np.sin(phase)*np.exp(-t*7) + .23*click
        elif p.kind == 'Snare':
            snap = self.filt(noise, 'high', 1200+3000*tone, .7, 0)
            x = .6*snap*np.exp(-t*13) + .6*np.sin(2*np.pi*(155+100*tone)*t)*np.exp(-t*24)
        elif p.kind == 'Hat':
            metal = sum(np.sin(2*np.pi*k*t) for k in (3211, 4327, 5879)) * .15
            x = self.filt(noise*.7+metal, 'high', 4500+5000*tone, .7, 0)*np.exp(-t*15)
        else:
            x = np.sin(ph*4 + (2+8*amount)*np.sin(ph*5.37))*np.exp(-t*4)
            x = self.filt(x, 'band', 400+4500*tone, 1.3, 0)*1.4
        env = np.minimum(t / .004, 1) * np.exp(-2.8*t/p.decay)
        env *= np.clip((p.decay-t)/.035, 0, 1)
        if self.kill_left is not None:
            env *= np.clip((self.kill_left-np.arange(n))/(.015*sr), 0, 1)
            self.kill_left = max(0, self.kill_left-n)
        x = np.tanh(x*(1+2.5*p.drive*grit))*.64*env*self.velocity*p.level
        self.age += n
        return np.column_stack((x*math.sqrt((1-p.pan)/2), x*math.sqrt((1+p.pan)/2)))


LAYER_LIMITS = dict(gain=(0,1), transpose=(-24,24), pan=(-1,1), tone=(0,1),
                    motion=(0,1), drive=(0,1), ratio=(.25,8), sweep=(-36,36), texture=(0,1))

def validate_layers(layers):
    if not isinstance(layers,list) or len(layers)>3:raise ValueError('At most three Forge layers')
    for layer in layers:
        if not isinstance(layer,dict) or layer.get('kind') not in KINDS:raise ValueError('Unknown layer engine')
        if set(layer) - (set(LAYER_LIMITS)|{'kind','enabled'}):raise ValueError('Unknown layer setting')
        if type(layer.get('enabled',True)) is not bool:raise ValueError('Invalid layer enable')
        for key,value in layer.items():
            if key in LAYER_LIMITS:
                lo,hi=LAYER_LIMITS[key]
                if not isinstance(value,(int,float)) or not lo<=value<=hi:raise ValueError('Invalid layer '+key)

class LayeredVoice:
    """Independent procedural voices mixed before the existing master effects."""
    def __init__(self,lane,patch,velocity,sr,seed):
        self.lane,self.p=lane,replace(patch)
        self.children=[]
        for i,layer in enumerate(patch.layers):
            if not layer.get('enabled',True):continue
            kwargs={k:layer[k] for k in ('tone','motion','drive','ratio','sweep','texture') if k in layer}
            child=replace(patch,kind=layer['kind'],layers=[],name='',
                          note=max(12,min(96,patch.note+layer.get('transpose',0))),
                          level=patch.level*layer.get('gain',.5),
                          pan=max(-1,min(1,patch.pan+layer.get('pan',0))),**kwargs)
            self.children.append(Voice(lane,child,velocity,sr,seed*3+i))
    @property
    def done(self):return all(v.done for v in self.children)
    def choke(self):
        for v in self.children:v.choke()
    def render(self,n,bpm,morph,grit):
        out=np.zeros((n,2))
        for v in self.children:
            if not v.done:out+=v.render(n,bpm,morph,grit)
        return out

def make_voice(lane,patch,velocity,sr,seed):
    return (LayeredVoice if patch.layers else Voice)(lane,patch,velocity,sr,seed)


class Engine:
    def __init__(self, sr=SR):
        self.sr = sr
        self.patches = kit()
        self.steps = pattern()
        self.muted = [False]*8
        self.bpm, self.swing = 140., 0.
        self.master, self.morph, self.grit = .65, 1., 1.
        self.delay_mix, self.feedback = .24, .35
        self.playing, self.overdub = False, False
        self.step, self.until_step = -1, 0.
        self.commands = queue.SimpleQueue()
        self.events = queue.SimpleQueue()
        self.voices = []
        self.delay = np.zeros((sr*3, 2))
        self.delay_pos = 0
        self.duck = 0.
        self.dc = np.zeros((2, 2))
        self.peak = 0.
        self.scope = np.zeros(256)
        self.seed = 0
        self.errors = ''
        self.xruns = 0
        self.recorder = None

    def trigger(self, lane, velocity=110, live=True):
        self.commands.put(('hit', lane, velocity, live))

    def start(self, lane, velocity):
        if self.muted[lane]: return
        # Monophonic per bass lane with a release tail; drums retain polyphony.
        if lane < 4 or self.patches[lane].kind == 'Hat':
            for v in self.voices:
                if v.lane == lane: v.choke()
        if len(self.voices) >= 32: self.voices.pop(0)
        self.seed += 1
        self.voices.append(make_voice(lane, self.patches[lane], velocity, self.sr, self.seed))
        if self.patches[lane].kind == 'Kick': self.duck = 1.
        self.events.put(('hit', lane, velocity))

    def handle(self):
        for _ in range(256):
            try: command = self.commands.get_nowait()
            except queue.Empty: break
            op, *args = command
            if op == 'hit':
                lane, velocity, live = args
                self.start(lane, velocity)
                if live and self.overdub and self.playing:
                    # Nearest straight-sixteenth quantization, preserving velocity.
                    unit = self.sr*60/self.bpm/4
                    step = (self.step + (1 if self.until_step < unit*.5 else 0)) % 32
                    self.steps[lane][step] = velocity
                    self.events.put(('step_edit', lane, step))
            elif op == 'play':
                self.playing = args[0]
                self.step, self.until_step = -1, 0.
            elif op == 'panic':
                self.voices.clear(); self.delay.fill(0); self.dc.fill(0); self.duck = 0
                self.playing = False; self.step = -1; self.until_step = 0.
            elif op == 'session':
                state = args[0]
                self.voices.clear(); self.delay.fill(0); self.dc.fill(0)
                self.patches = [Patch(**p) for p in state['patches']]
                self.steps = state['steps']; self.muted = state['muted']
                for key in ('bpm','swing','master','morph','grit','delay_mix','feedback'):
                    setattr(self, key, state[key])
                self.playing = False; self.step = -1; self.until_step = 0.

    def segment(self, n):
        dry = np.zeros((n, 2)); wet = np.zeros((n, 2))
        duck = 1 - .7*self.duck*np.exp(-np.arange(n)/(self.sr*.075))
        self.duck *= math.exp(-n/(self.sr*.075))
        for v in self.voices:
            x = v.render(n, self.bpm, self.morph, self.grit)
            if v.lane < 4: x *= duck[:, None]
            dry += x
            wet += x*v.p.send
        self.voices = [v for v in self.voices if not v.done]
        # The short render chunks are smaller than the minimum delay tap.
        positions = (self.delay_pos + np.arange(n)) % len(self.delay)
        delay_samples = int(self.sr*60/self.bpm*.75)
        echo = self.delay[(positions-delay_samples) % len(self.delay)].copy()
        self.delay[positions] = np.tanh(wet + echo[:, ::-1]*self.feedback)
        self.delay_pos = (self.delay_pos+n) % len(self.delay)
        mix = dry + echo*self.delay_mix
        mix, self.dc = lfilter([1, -1], [1, -.997], mix, axis=0, zi=self.dc[:1])
        return .94*np.tanh(mix*self.master*1.5)

    def render(self, n):
        self.handle()
        result = np.zeros((n, 2), dtype=np.float32)
        offset = 0
        while offset < n:
            if self.playing and self.until_step <= 0:
                self.step = (self.step+1) % 32
                for lane in range(8):
                    vel = self.steps[lane][self.step]
                    if vel: self.start(lane, vel)
                self.until_step += self.sr*60/self.bpm/4*(1+self.swing*(1 if self.step%2 == 0 else -1))
            count = min(128, n-offset)
            if self.playing: count = min(count, max(1, math.ceil(self.until_step)))
            result[offset:offset+count] = self.segment(count)
            if self.playing: self.until_step -= count
            offset += count
        self.peak = float(np.max(np.abs(result))) if n else 0
        self.scope = result[::max(1,n//256), 0].copy()
        return result

    def callback(self, outdata, frames, time_info, status):
        if status: self.xruns += 1
        try:
            outdata[:] = self.render(frames)
            if self.recorder is not None: self.recorder.push(outdata)
        except Exception as exc:
            outdata.fill(0)
            self.errors = str(exc)

    def state(self):
        return dict(version=1, patches=[asdict(p) for p in self.patches],
                    steps=[r[:] for r in self.steps], muted=self.muted[:],
                    **{k:getattr(self,k) for k in ('bpm','swing','master','morph','grit','delay_mix','feedback')})


def validate_state(state):
    if not isinstance(state, dict) or state.get('version') != 1: raise ValueError('Unsupported session version')
    if len(state['patches']) != 8 or len(state['steps']) != 8: raise ValueError('Expected eight lanes')
    limits = dict(note=(12,96), decay=(.06,6), tone=(0,1), motion=(0,1), drive=(0,1), rate=(.5,8), level=(0,1), pan=(-1,1), send=(0,.8), ratio=(.25,8), sweep=(-36,36), texture=(0,1))
    for raw in state['patches']:
        p = Patch(**raw)
        validate_layers(p.layers)
        if not isinstance(p.name,str) or len(p.name)>100:raise ValueError('Invalid instrument name')
        if p.kind not in KINDS: raise ValueError('Unknown synth')
        for k,(lo,hi) in limits.items():
            v = getattr(p,k)
            if not isinstance(v,(float,int)) or not lo <= v <= hi: raise ValueError('Invalid '+k)
    for row in state['steps']:
        if len(row)!=32 or any(type(v)!=int or not 0<=v<=127 for v in row): raise ValueError('Invalid steps')
    if len(state['muted'])!=8 or any(type(v)!=bool for v in state['muted']): raise ValueError('Invalid mute state')
    for k,lo,hi in [('bpm',50,200),('swing',0,.45),('master',0,1),('morph',0,1.5),('grit',0,1.5),('delay_mix',0,.8),('feedback',0,.75)]:
        if not isinstance(state[k],(float,int)) or not lo<=state[k]<=hi: raise ValueError('Invalid '+k)
    return state
