#!/usr/bin/env python3
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import sys
import wave
import time
import shutil
import numpy as np
from engine import Engine, Patch, KINDS, RATES, kit, pattern, validate_state
from io_layer import MidiRouter, Recorder

ROOT = Path(__file__).resolve().parent
PAD_COLORS = ['#a78bfa','#4cc9f0','#f59e7a','#e879c3','#71d6a6','#f2cd68','#7ba5f5','#c3d879']
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'oceanboiler'


def render_demo(path):
    e = Engine()
    e.commands.put(('play',True))
    blocks = []
    # Four bars then delay tails; deterministic seed for repeatable rendering.
    total = round(e.sr*60/e.bpm*16)
    while total:
        n = min(256,total); blocks.append(e.render(n)); total -= n
    e.commands.put(('play',False))
    for _ in range(375): blocks.append(e.render(256))
    a = np.concatenate(blocks)
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(e.sr)
        f.writeframes((np.clip(a,-1,1)*32767).astype('<i2').tobytes())
    print(f'Rendered {path}: {len(a)/e.sr:.2f}s; peak {np.max(np.abs(a)):.3f}')


def main():
    parser = argparse.ArgumentParser(description='OCEANBOILER: KTMP1 bass workstation')
    parser.add_argument('--render-demo',metavar='WAV')
    parser.add_argument('--no-audio',action='store_true',help='Edit/inspect without audio hardware')
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.render_demo: render_demo(args.render_demo); return
    from panels import InstrumentPanel, HardwarePanel
    from forge import SoundForge
    from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
    try:
        import sounddevice as sd
    except OSError:
        sd = None
    import mido

    class Scope(W.QWidget):
        def __init__(self,e):
            super().__init__(); self.e=e; self.setMinimumHeight(64)
        def paintEvent(self,event):
            p=G.QPainter(self); p.fillRect(self.rect(),G.QColor('#0a1017'))
            p.setPen(G.QPen(G.QColor('#243240'),1)); p.drawLine(0,self.height()//2,self.width(),self.height()//2)
            a=self.e.scope
            if len(a)<2:return
            path=G.QPainterPath(); path.moveTo(0,self.height()/2-float(a[0])*self.height()*.46)
            for i,v in enumerate(a):path.lineTo(i*self.width()/(len(a)-1),self.height()/2-float(v)*self.height()*.46)
            p.setRenderHint(G.QPainter.Antialiasing);p.setPen(G.QPen(G.QColor('#8bf6c0'),1.5));p.drawPath(path)

    class StepGrid(W.QWidget):
        def __init__(self,e):
            super().__init__();self.e=e;self.setMinimumSize(760,245)
        def paintEvent(self,event):
            p=G.QPainter(self); cw=self.width()/32;ch=self.height()/8
            p.fillRect(self.rect(),G.QColor('#101720'))
            for r in range(8):
                for s in range(32):
                    v=self.e.steps[r][s]
                    color=G.QColor(PAD_COLORS[r]) if v else G.QColor('#283340' if s%4==0 else '#1b2530')
                    if v:color.setAlpha(100+int(v/127*155))
                    p.fillRect(C.QRectF(s*cw+2,r*ch+3,cw-4,ch-6),color)
                    if self.e.playing and s==self.e.step:
                        p.setPen(G.QPen(G.QColor('#f8e8b4'),2));p.drawRect(C.QRectF(s*cw+1,r*ch+2,cw-2,ch-4))
        def mousePressEvent(self,event):
            s=int(event.position().x()*32/self.width());r=int(event.position().y()*8/self.height())
            if not(0<=s<32 and 0<=r<8):return
            v=self.e.steps[r][s]
            self.e.steps[r][s]= (55 if v==0 or v>=110 else 85 if v==55 else 120) if event.button()==C.Qt.RightButton else (0 if v else 110)
            self.update()

    class Window(W.QMainWindow):
        def __init__(self):
            super().__init__()
            self.e=Engine();self.router=MidiRouter(self.e);self.stream=None;self.port=None
            self.audio_devices=[];self.selected=0;self.seq_learn=False;self.recording=None;self.record_started=0
            self.controls={};self.loading=False;self.flashes=[0]*8;self.tick_count=0
            self.setWindowTitle('OCEANBOILER 0.3 · KTMP1 Bass Workstation');self.resize(1250,900)
            outer=W.QWidget();self.setCentralWidget(outer);layout=W.QVBoxLayout(outer);layout.setSpacing(9)
            top=W.QHBoxLayout();layout.addLayout(top)
            title=W.QLabel('OCEANBOILER');title.setObjectName('title');top.addWidget(title)
            subtitle=W.QLabel('SUB PRESSURE / PAD-DRIVEN BASS LAB');subtitle.setObjectName('muted');top.addWidget(subtitle);top.addStretch()
            top.addWidget(self.button('Save',self.save));top.addWidget(self.button('Load',self.load));top.addWidget(self.button('PANIC · Esc',self.panic))
            self.pages=W.QTabWidget()
            perform=W.QWidget();bl=W.QVBoxLayout(perform)
            sounds=W.QWidget();sound_layout=W.QVBoxLayout(sounds)
            beats=W.QWidget();beat_layout=W.QVBoxLayout(beats)
            setup=W.QWidget();setup_layout=W.QVBoxLayout(setup)
            for widget,name in [(perform,'PLAY'),(sounds,'SOUNDS'),(beats,'BEAT'),(setup,'SETUP')]:self.pages.addTab(widget,name)
            self.lane_picker=W.QComboBox();self.lane_picker.addItems([f'Sound lane {i+1}' for i in range(8)]);self.lane_picker.currentIndexChanged.connect(self.select);sound_layout.addWidget(self.lane_picker)
            conn=W.QHBoxLayout();setup_layout.addLayout(conn)
            conn.addWidget(W.QLabel('MIDI'));self.midi=W.QComboBox();self.midi.setMinimumWidth(190);conn.addWidget(self.midi,1)
            conn.addWidget(self.button('Connect',self.connect_midi));conn.addWidget(self.button('Refresh',self.refresh))
            conn.addWidget(W.QLabel('Output'));self.output=W.QComboBox();conn.addWidget(self.output,1)
            self.buffer=W.QComboBox();self.buffer.addItems(['128','256','512','1024']);self.buffer.setCurrentText('256');conn.addWidget(self.buffer)
            conn.addWidget(self.button('Start audio',self.start_audio))
            transport=W.QHBoxLayout();layout.addLayout(transport)
            self.play=self.button('▶ Play',self.toggle_play);transport.addWidget(self.play)
            self.overdub=W.QCheckBox('Overdub hits');self.overdub.toggled.connect(lambda v:setattr(self.e,'overdub',v));beat_layout.addWidget(self.overdub)
            transport.addWidget(W.QLabel('BPM'));self.tempo=W.QSpinBox();self.tempo.setRange(50,200);self.tempo.setValue(140);self.tempo.valueChanged.connect(lambda v:setattr(self.e,'bpm',v));transport.addWidget(self.tempo)
            self.kits=W.QComboBox();self.kits.addItems(['Abyss','Bog ritual','Chrome teeth','Deep pressure']);sound_layout.addWidget(self.kits)
            sound_layout.addWidget(self.button('Load kit',self.load_kit));beat_layout.addWidget(self.button('Demo beat',self.demo_beat));beat_layout.addWidget(self.button('Clear beat',self.clear_beat))
            self.rec=self.button('●  RECORD AUDIO',self.record);self.rec.setMinimumSize(240,52);self.rec.setStyleSheet('background:#882b42;color:white;font-size:17px;font-weight:bold;border:2px solid #ef7792;');transport.addWidget(self.rec);self.ready=W.QLabel('Audio off · MIDI disconnected');transport.addWidget(self.ready,1)
            layout.addWidget(self.pages,1)
            welcome=W.QHBoxLayout();bl.addLayout(welcome)
            welcome.addWidget(W.QLabel('1  Connect in SETUP     2  Learn your pads     3  Hit a pad or press 1–8'),1)
            welcome.addWidget(self.button('Learn 4 KAT pads',self.learn_four));welcome.addWidget(self.button('Cancel learn',self.cancel_learn))
            welcome.addWidget(self.button('Change selected sound →',lambda:self.pages.setCurrentIndex(1)))
            self.scope=Scope(self.e);self.scope.setFixedHeight(60);bl.addWidget(self.scope)
            macro=W.QHBoxLayout();bl.addLayout(macro);advanced_macro=W.QHBoxLayout();beat_layout.addLayout(advanced_macro)
            self.macros={}
            for label,key,lo,hi in [('MASTER','master',0,100),('MOTION','morph',0,150),('GRIT','grit',0,150),('SPACE','delay_mix',0,80),('FEEDBACK','feedback',0,75),('SWING','swing',0,45)]:
                box=W.QVBoxLayout();(advanced_macro if key in ('feedback','swing') else macro).addLayout(box);box.addWidget(W.QLabel(label));slider=W.QSlider(C.Qt.Horizontal);slider.setRange(lo,hi);slider.setValue(round(getattr(self.e,key)*100));slider.valueChanged.connect(lambda v,k=key:setattr(self.e,k,v/100));box.addWidget(slider);self.macros[key]=slider
            pads=W.QGridLayout();pads.setSpacing(12);bl.addLayout(pads,1);self.padbuttons=[]
            for i in range(8):
                b=self.button('',lambda _,i=i:self.hit(i));b.setMinimumHeight(140);b.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Expanding);b.setObjectName('pad');pads.addWidget(b,i//4,i%4);self.padbuttons.append(b)
            self.instruments=InstrumentPanel(self,CONFIG);self.hardware=HardwarePanel(self)
            sound_layout.addWidget(self.instruments);setup_layout.addWidget(self.hardware)
            edit=W.QGroupBox('VOICE DESIGN · selected software lane');sound_layout.addWidget(edit);ed=W.QGridLayout(edit)
            self.kind=W.QComboBox();self.kind.addItems(KINDS);self.kind.currentTextChanged.connect(lambda v:self.edit_patch('kind',v));ed.addWidget(W.QLabel('Engine'),0,0);ed.addWidget(self.kind,1,0)
            self.rate=W.QComboBox();self.rate.addItems([str(v)+' × beat' for v in RATES]);self.rate.currentIndexChanged.connect(lambda i:self.edit_patch('rate',RATES[i]));ed.addWidget(W.QLabel('Wobble speed'),0,1);ed.addWidget(self.rate,1,1)
            for col,(label,key,lo,hi,scale) in enumerate([('Pitch · MIDI','note',12,96,1),('Length · s','decay',6,600,100),('Tone','tone',0,100,100),('Motion','motion',0,100,100),('Drive','drive',0,100,100),('Level','level',0,100,100),('Pan','pan',-100,100,100),('Delay send','send',0,80,100),('FM ratio*','ratio',25,800,100),('Sweep · st*','sweep',-3600,3600,100),('Texture*','texture',0,100,100)],2):
                row=(col//6)*2;column=col%6
                ed.addWidget(W.QLabel(label),row,column);sp=W.QDoubleSpinBox() if scale==100 else W.QSpinBox()
                sp.setRange(lo/scale if scale==100 else lo,hi/scale if scale==100 else hi);sp.setSingleStep(.01 if scale==100 else 1);sp.valueChanged.connect(lambda v,k=key:self.edit_patch(k,v));ed.addWidget(sp,row+1,column);self.controls[key]=sp
            learn=W.QHBoxLayout();setup_layout.addLayout(learn)
            learn.addWidget(self.button('Learn selected pad',self.learn_selected));learn.addWidget(self.button('Learn all 4 KAT pads',self.learn_four));learn.addWidget(self.button('Cancel learn',self.cancel_learn));learn.addWidget(self.button('Reset mapping',self.reset_mapping))
            self.mapping_label=W.QLabel('');learn.addWidget(self.mapping_label,1)
            seqtitle=W.QLabel('TWO-BAR SEQUENCER  /  32 SIXTEENTHS  /  click on/off · right-click velocity');seqtitle.setObjectName('muted');beat_layout.addWidget(seqtitle)
            seqrow=W.QHBoxLayout();beat_layout.addLayout(seqrow,1);names=W.QVBoxLayout();seqrow.addLayout(names)
            self.mutes=[]
            for i in range(8):
                ck=W.QCheckBox(f'MUTE {i+1}  {self.e.patches[i].kind}');ck.setToolTip('Check to mute this lane');ck.toggled.connect(lambda v,i=i:self.set_mute(i,v));names.addWidget(ck);self.mutes.append(ck)
            self.grid=StepGrid(self.e);seqrow.addWidget(self.grid,1)
            settings=W.QHBoxLayout();setup_layout.addLayout(settings)
            for label,lo,hi,val,attr in [('Channel (0=all)',0,16,10,'channel'),('Min velocity',1,127,1,'threshold'),('Retrigger ms',0,100,0,'retrigger_ms')]:
                settings.addWidget(W.QLabel(label));sp=W.QSpinBox();sp.setRange(lo,hi);sp.setValue(val);sp.valueChanged.connect(lambda v,k=attr:setattr(self.router,k,v));settings.addWidget(sp);setattr(self,'midi_'+attr,sp)
            settings.addWidget(W.QLabel('Velocity curve'));self.curve=W.QDoubleSpinBox();self.curve.setRange(.2,2);self.curve.setSingleStep(.05);self.curve.setValue(.75);self.curve.valueChanged.connect(lambda v:setattr(self.router,'curve',v));settings.addWidget(self.curve)
            self.monitor=W.QPlainTextEdit();self.monitor.setReadOnly(True);self.monitor.setMaximumBlockCount(100);self.monitor.setMaximumHeight(140);setup_layout.addWidget(self.monitor);setup_layout.addStretch()
            self.forge=SoundForge(self);self.pages.addTab(self.forge,'SOUND FORGE')
            self.status=W.QLabel('Starting…');layout.addWidget(self.status)
            self.notice=W.QLabel('Hit keys 1–8 or the pads. Space = transport. Learn the KAT before playing.');self.notice.setWordWrap(True);layout.addWidget(self.notice)
            self.select(0);self.refresh()
            self.restore_autosave()
            self.timer=C.QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(33)
            self.autosave=C.QTimer(self);self.autosave.timeout.connect(self.write_autosave);self.autosave.start(30000)
            # Event filter avoids retrigger from keyboard auto-repeat and editing numeric fields.
            W.QApplication.instance().installEventFilter(self)
            if not args.no_audio:C.QTimer.singleShot(150,self.start_audio)
            if not args.smoke_test:C.QTimer.singleShot(350,self.auto_midi)

        def button(self,text,fn):
            b=W.QPushButton(text);b.clicked.connect(fn);return b
        def tell(self,text):self.notice.setText(text)
        def hit(self,i):self.select(i);self.e.trigger(i)
        def select(self,i):
            self.selected=i;self.lane_picker.blockSignals(True);self.lane_picker.setCurrentIndex(i);self.lane_picker.blockSignals(False);self.loading=True;p=self.e.patches[i]
            self.kind.setCurrentText(p.kind);self.rate.setCurrentIndex(min(range(len(RATES)),key=lambda j:abs(RATES[j]-p.rate)))
            for k,sp in self.controls.items():sp.setValue(getattr(p,k))
            for key,kinds in [('ratio',('Weeewhaa','Bubble','Neuro')),('sweep',('Weeewhaa','Bubble')),('texture',('Rubber wub','Scratch','Weeewhaa','Bubble','Neuro'))]:
                self.controls[key].setEnabled(p.kind in kinds)
                self.controls[key].setToolTip('Used by: '+', '.join(kinds))
            layered=bool(p.layers);self.kind.setEnabled(not layered);self.rate.setEnabled(not layered)
            if layered:
                for widget in self.controls.values():widget.setEnabled(False)
            else:
                for key in ('note','decay','tone','motion','drive','level','pan','send'):self.controls[key].setEnabled(True)
            self.kind.setToolTip('Custom layered instrument: edit in SOUND FORGE' if layered else 'Synthesis engine')
            self.loading=False;self.update_labels()
        def edit_patch(self,k,v):
            if not self.loading:
                setattr(self.e.patches[self.selected],k,v)
                if k=='kind':self.select(self.selected)
                else:self.update_labels()
        def update_labels(self):
            self.hardware.reconcile()
            for i,b in enumerate(self.padbuttons):
                notes=[str(n) for n,l in self.router.mapping.items() if l==i]
                assigned=[self.hardware.LABELS[j] for j,n in enumerate(self.hardware.notes) if n>=0 and self.hardware.targets[j]==i]
                route=' / '.join(assigned) if assigned else ('MIDI '+','.join(notes) if notes else 'Key '+str(i+1)+' · KAT not learned')
                if self.router.learn==i:route='HIT YOUR KAT PAD NOW'
                label=(self.e.patches[i].name or self.e.patches[i].kind).upper()
                if self.e.muted[i]:route='MUTED — uncheck MUTE in BEAT'
                b.setText(f'{i+1}   {label}\n\n'+route)
                b.setToolTip('Software sound lane '+str(i+1)+'. Click to play and select; change its instrument in SOUNDS.')
                self.paint_pad(i)
                self.mutes[i].setText(f'MUTE {i+1}  {self.e.patches[i].name or self.e.patches[i].kind}')
            self.mapping_label.setText('Learning lane: '+str(self.router.learn+1) if self.router.learn is not None else '8 software lanes · assign the 6 KAT connections in the KAT tab')
        def set_mute(self,i,value):
            self.e.muted[i]=value;self.update_labels()
        def paint_pad(self,i):
            color=G.QColor(PAD_COLORS[i]);flash=self.flashes[i]>0
            bg=G.QColor('#252830') if self.e.muted[i] else (color if flash else color.darker(340))
            border='#ffe884' if self.router.learn==i else ('#ffffff' if i==self.selected else color.name())
            css=f'background:{bg.name()};color:{"#111720" if flash else color.lighter(120).name()};border:{4 if i==self.selected else 2}px solid {border};border-radius:12px;font-size:15px;font-weight:bold;'
            b=self.padbuttons[i]
            if b.styleSheet()!=css:b.setStyleSheet(css)
        def toggle_play(self):self.e.commands.put(('play',not self.e.playing))
        def panic(self):self.e.commands.put(('panic',));self.overdub.setChecked(False);self.tell('All voices and delay cleared; transport stopped.')
        def load_kit(self):
            self.e.patches=kit(self.kits.currentText());self.select(self.selected);self.tell('Kit loaded. MIDI mapping and beat retained.')
        def demo_beat(self):self.e.steps=pattern();self.grid.update()
        def clear_beat(self):self.e.steps=[[0]*32 for _ in range(8)];self.grid.update()
        def learn_selected(self):self.seq_learn=False;self.router.learn=self.selected;self.update_labels();self.tell('Strike the physical pad you want mapped to this voice.')
        def learn_four(self):self.seq_learn=True;self.router.learn=0;self.select(0);self.tell('Strike KAT pad 1, then 2, then 3, then 4. Each must send a distinct note.')
        def cancel_learn(self):self.seq_learn=False;self.router.learn=None;self.router.learn_source=False;self.hardware.pending=None;self.update_labels()
        def reset_mapping(self):self.router.mapping={};self.router.last={};self.hardware.restore({});self.cancel_learn();self.tell('Mapping cleared. Use Learn all 4 KAT pads.')
        def refresh(self):
            current=self.midi.currentText();self.midi.clear()
            try:self.midi.addItems(mido.get_input_names())
            except Exception as exc:self.tell('MIDI unavailable: '+str(exc))
            if current:self.midi.setCurrentText(current)
            if self.stream:return
            self.output.clear();self.audio_devices=[]
            try:
                if sd is None:raise RuntimeError('PortAudio missing. Install the system portaudio package.')
                apis=sd.query_hostapis()
                for i,d in enumerate(sd.query_devices()):
                    if d['max_output_channels']>=2:
                        self.audio_devices.append(i);self.output.addItem(f"{apis[d['hostapi']]['name']} · {d['name']}")
                best=next((i for i in range(self.output.count()) if 'JACK' in self.output.itemText(i).upper()),None)
                if best is None:best=next((i for i in range(self.output.count()) if 'pipewire' in self.output.itemText(i).lower()),None)
                if best is None:best=next((i for i in range(self.output.count()) if 'default' in self.output.itemText(i).lower()),0)
                self.output.setCurrentIndex(best)
            except Exception as exc:self.tell('Audio discovery: '+str(exc))
        def auto_midi(self):
            for i in range(self.midi.count()):
                if any(n in self.midi.itemText(i).lower() for n in ('kat','ktmp','usb midi','usb-midi')):
                    self.midi.setCurrentIndex(i);self.connect_midi();break
        def connect_midi(self):
            try:
                if self.port:self.port.close();self.port=None
                name=self.midi.currentText()
                if not name:self.tell('No MIDI input found. Check USB and power; press Refresh.');return
                self.port=mido.open_input(name,callback=self.router.receive);self.tell('Connected '+name+'. Use Learn all 4 KAT pads.')
            except Exception as exc:self.tell('MIDI connection failed: '+str(exc))
        def start_audio(self):
            if self.recording:self.tell('Stop WAV recording before changing the audio output.');return
            try:
                if self.stream:self.stream.stop();self.stream.close();self.stream=None
                if not self.audio_devices:raise RuntimeError('No stereo output. Check PipeWire, then restart the app.')
                idx=self.audio_devices[self.output.currentIndex()]
                self.stream=sd.OutputStream(device=idx,samplerate=48000,channels=2,dtype='float32',blocksize=int(self.buffer.currentText()),latency='low',callback=self.e.callback)
                self.stream.start();self.tell('Audio running. Use keys 1–8 to audition, or learn your KAT pads.')
            except Exception as exc:
                if self.stream:self.stream.close();self.stream=None
                self.tell('Audio failed: '+str(exc)+' — try another output or a 512-frame buffer.')
        def record(self):
            if self.recording:
                self.e.recorder=None;r=self.recording;self.recording=None;r.close();self.rec.setText('●  RECORD AUDIO');self.rec.setStyleSheet('background:#882b42;color:white;font-size:17px;font-weight:bold;border:2px solid #ef7792;')
                self.tell('WAV saved.' if not r.error and not r.dropped else f'Recording issue: {r.error}; dropped blocks: {r.dropped}');return
            if not self.stream:self.tell('Start audio before recording.');return
            path,_=W.QFileDialog.getSaveFileName(self,'Record stereo output','oceanboiler-take.wav','WAV (*.wav)')
            if path:
                try:self.recording=Recorder(path,self.e.sr);self.e.recorder=self.recording;self.record_started=time.monotonic();self.rec.setText('■  STOP · 00:00');self.rec.setStyleSheet('background:#e13b59;color:white;font-size:17px;font-weight:bold;border:3px solid white;');self.tell('Recording the master output to 24-bit WAV.')
                except Exception as exc:self.tell('Recording failed: '+str(exc))
        def session(self):
            state=self.e.state();state['hardware']=self.hardware.state();state['mapping']={str(k):v for k,v in self.router.mapping.items()}
            state['midi_settings']={k:getattr(self.router,k) for k in ('channel','threshold','curve','retrigger_ms')}
            return state
        def apply_session(self,state):
            validate_state(state)
            HardwarePanel.validate(state.get('hardware',{}))
            mapping={int(k):int(v) for k,v in state.get('mapping',{}).items()}
            if any(not 0<=k<=127 or not 0<=v<8 for k,v in mapping.items()):raise ValueError('Invalid MIDI map')
            settings=state.get('midi_settings',{})
            for k,lo,hi in [('channel',0,16),('threshold',1,127),('curve',.2,2),('retrigger_ms',0,100)]:
                v=settings.get(k,getattr(self.router,k))
                if not isinstance(v,(int,float)) or not lo<=v<=hi:raise ValueError('Invalid MIDI setting '+k)
            self.hardware.restore(state.get('hardware',{}))
            self.router.mapping=mapping;self.cancel_learn();self.e.commands.put(('session',state))
            # With audio off the GUI owns the engine; otherwise apply at callback boundary.
            if self.stream is None:self.e.handle()
            for k,v in settings.items():
                if k in ('channel','threshold','retrigger_ms'):getattr(self,'midi_'+k).setValue(int(v))
                elif k=='curve':self.curve.setValue(v)
            C.QTimer.singleShot(80,self.sync_controls)
        def sync_controls(self):
            self.tempo.setValue(round(self.e.bpm))
            for k,s in self.macros.items():s.setValue(round(getattr(self.e,k)*100))
            for i,c in enumerate(self.mutes):c.setChecked(self.e.muted[i])
            self.select(self.selected);self.grid.update()
        def save(self):
            path,_=W.QFileDialog.getSaveFileName(self,'Save session','oceanboiler-session.json','Session (*.json)')
            if path:
                try:Path(path).write_text(json.dumps(self.session(),indent=2));self.tell('Session saved: '+path)
                except Exception as exc:self.tell('Save failed: '+str(exc))
        def load(self):
            path,_=W.QFileDialog.getOpenFileName(self,'Load session','','Session (*.json)')
            if path:
                try:self.apply_session(json.loads(Path(path).read_text()));self.tell('Session loaded.')
                except Exception as exc:self.tell('Load failed: '+str(exc))
        def write_autosave(self):
            if args.smoke_test:return
            try:
                CONFIG.mkdir(parents=True,exist_ok=True);temp=CONFIG/'autosave.tmp';temp.write_text(json.dumps(self.session()));temp.replace(CONFIG/'autosave.json')
            except Exception as exc:self.tell('Autosave failed: '+str(exc))
        def restore_autosave(self):
            path=CONFIG/'autosave.json'
            if path.exists() and not args.smoke_test:
                try:
                    contents=path.read_text();saved=json.loads(contents)
                    backup=CONFIG/'autosave-before-0.2.json'
                    if 'hardware' not in saved and not backup.exists():backup.write_text(contents)
                    self.apply_session(saved)
                except Exception as exc:self.tell('Could not restore autosave: '+str(exc))
        def poll(self):
            self.tick_count+=1
            for _ in range(256):
                try:event=self.router.log.get_nowait()
                except queue.Empty:break
                if event[0]=='midi':self.monitor.appendPlainText(f'CH {event[1]:02d}  NOTE {event[2]:03d}  VEL {event[3]:03d}  {event[4]}')
                elif event[0]=='cc':self.monitor.appendPlainText(f'CH {event[1]:02d}  CC {event[2]:03d}  VALUE {event[3]:03d}')
                elif event[0]=='collision':self.tell(f'Note {event[1]} already maps to voice {event[2]+1}. Set distinct MIDI notes on the KAT, or reset mapping.')
                elif event[0]=='learned':
                    if self.seq_learn and event[2]<4:
                        row=event[2];self.hardware.rows[row][1].setCurrentIndex(row);self.hardware.rows[row][0].setValue(event[1])
                    self.hardware.learned(event[1],event[2])
                    lane=event[2];self.tell(f'Learned note {event[1]} → voice {lane+1}.')
                    if self.seq_learn and lane<3:self.router.learn=lane+1;self.select(lane+1)
                    else:self.seq_learn=False;self.update_labels()
            for _ in range(512):
                try:event=self.e.events.get_nowait()
                except queue.Empty:break
                if event[0]=='hit':self.flashes[event[1]]=4
            for i,b in enumerate(self.padbuttons):
                self.paint_pad(i)
                self.flashes[i]=max(0,self.flashes[i]-1)
            self.play.setText('■ Stop' if self.e.playing else '▶ Play');self.scope.update();self.grid.update()
            if self.e.errors:self.tell('Audio engine error: '+self.e.errors)
            if self.tick_count%10==0:
                if self.recording:
                    elapsed=int(time.monotonic()-self.record_started);self.rec.setText(f'■  STOP · {elapsed//60:02d}:{elapsed%60:02d}')
                ready=bool(self.stream and self.stream.active)
                self.ready.setText(('● Audio ready' if ready else '○ Audio off — SETUP')+'   /   '+('● MIDI connected' if self.port else '○ MIDI off — SETUP'))
                self.ready.setStyleSheet('color:'+('#8bf6c0' if ready and self.port else '#f2cd68')+';')
                cpu=self.stream.cpu_load*100 if self.stream else 0
                latency=self.stream.latency*1000 if self.stream else 0
                peak=20*np.log10(max(1e-6,self.e.peak))
                self.status.setText(f"{'AUDIO ON' if self.stream else 'AUDIO OFF'}  ·  48 kHz  ·  reported output {latency:.1f} ms  ·  DSP {cpu:.0f}%  ·  xruns {self.e.xruns}  ·  peak {peak:.1f} dBFS  ·  voices {len(self.e.voices)}  ·  {'MIDI connected' if self.port else 'MIDI disconnected'}")
        def eventFilter(self,obj,event):
            if event.type()==C.QEvent.KeyPress:
                if event.key()==C.Qt.Key_Escape:self.panic();return True
                if isinstance(W.QApplication.focusWidget(),(W.QLineEdit,W.QAbstractSpinBox,W.QPlainTextEdit,W.QComboBox)):return False
                if event.isAutoRepeat():return event.key() in [C.Qt.Key_Space]+list(range(C.Qt.Key_1,C.Qt.Key_8+1))
                if C.Qt.Key_1<=event.key()<=C.Qt.Key_8:self.hit(event.key()-C.Qt.Key_1);return True
                if event.key()==C.Qt.Key_Space:self.toggle_play();return True
            return super().eventFilter(obj,event)
        def closeEvent(self,event):
            self.timer.stop();self.autosave.stop();self.write_autosave()
            if self.port:self.port.close()
            if self.stream:self.stream.stop();self.stream.close()
            if self.recording:self.e.recorder=None;self.recording.close()
            event.accept()

    app=W.QApplication(sys.argv);app.setApplicationName('Oceanboiler');app.setStyle('Fusion')
    app.setStyleSheet('''
      QWidget { background:#101720; color:#d9e4eb; font-family:DejaVu Sans; font-size:12px; }
      QLabel#title {font-size:30px; font-weight:900; color:#a78bfa; letter-spacing:3px;}
      QLabel#muted {color:#8195a6; font-size:11px;}
      QPushButton {background:#223140;border:1px solid #344556;border-radius:5px;padding:8px;}
      QPushButton:hover {background:#35465a;border-color:#9b7cec;}
      QPushButton:pressed {background:#7357b2;}
      QPushButton#pad {font-weight:bold;background:#202338;border:1px solid #494062;}
      QPushButton#pad[selected="true"] {border:2px solid #b599ff;background:#332b48;}
      QWidget:disabled {color:#65707a;}
      QComboBox,QSpinBox,QDoubleSpinBox {background:#192531;border:1px solid #354656;padding:5px;}
      QGroupBox {border:1px solid #334353;border-radius:6px;margin-top:10px;padding-top:12px;}
      QGroupBox::title {subcontrol-origin:margin;left:10px;color:#9cacbb;}
      QSlider::groove:horizontal {height:5px;background:#283c49;}
      QSlider::handle:horizontal {background:#91e6be;width:12px;margin:-5px 0;border-radius:3px;}
      QPlainTextEdit {background:#0a1017;color:#8da7b8;border:1px solid #283745;font-family:monospace;}
      QTabBar::tab {padding:10px 28px;background:#192531;color:#91a3b5;} QTabBar::tab:selected {background:#35445a;color:white;border-bottom:3px solid #91e6be;} QScrollArea {border:0;} QCheckBox::indicator:checked {background:#a78bfa;}
    ''')
    G.QIcon.setThemeSearchPaths([]);G.QIcon.setFallbackSearchPaths([])
    G.QIcon.setThemeName('oceanboiler-builtin');G.QIcon.setFallbackThemeName('')
    if not args.smoke_test:
        legacy=CONFIG.parent/'wubforge'
        if legacy.is_dir() and not (CONFIG/'migration-complete').exists():
            try:
                CONFIG.mkdir(parents=True,exist_ok=True)
                for name in ('autosave.json','user-presets.json'):
                    if (legacy/name).is_file() and not (CONFIG/name).exists():shutil.copy2(legacy/name,CONFIG/name)
                (CONFIG/'migration-complete').write_text('Copied legacy settings without changing originals.\n')
            except OSError as exc:print('Settings migration failed:',exc,file=sys.stderr)
    win=Window();win.show()
    if args.smoke_test:
        def smoke():
            try:
                win.hit(0);win.e.render(256);win.instruments.load();win.forge.apply();win.e.trigger(0);win.e.render(256);win.forge.load_current();win.hardware.rows[0][0].setValue(36)
                win.hardware.rows[0][1].setCurrentIndex(2)
                assert win.router.mapping[36]==2
                win.apply_session(win.session());win.sync_controls()
                win.grab().save(str(ROOT/'ui-preview.png'));win.pages.setCurrentIndex(4);app.processEvents();win.grab().save(str(ROOT/'forge-preview.png'))
                print('GUI smoke test passed: construct, hit, render, session roundtrip, screenshot',flush=True)
            finally:win.close();app.quit()
        C.QTimer.singleShot(250,smoke)
    sys.exit(app.exec())

if __name__=='__main__':main()
