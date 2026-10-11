"""Three-layer custom instrument authoring. Patch-only JSON, no executable plugins."""
import json
from dataclasses import asdict
from pathlib import Path
from PySide6 import QtWidgets as W
from engine import Patch, KINDS, RATES, validate_state

class SoundForge(W.QWidget):
    def __init__(self,win):
        super().__init__();self.win=win;self.rows=[]
        layout=W.QVBoxLayout(self)
        intro=W.QLabel('Build a custom voice: blend SUB + BODY + TEXTURE, then Apply to a sound lane. Every layer is synthesized.');intro.setWordWrap(True);layout.addWidget(intro)
        top=W.QHBoxLayout();layout.addLayout(top)
        self.name=W.QLineEdit('Boiling point');self.name.setMaxLength(100);top.addWidget(self.name,2)
        self.target=W.QComboBox();self.target.addItems([f'Lane {i+1}' for i in range(8)]);top.addWidget(self.target)
        self.pitch=self.spin(12,96,29,1);self.decay=self.spin(.06,6,1.6,.05);self.rate=W.QComboBox();self.rate.addItems([str(v)+' × beat' for v in RATES]);self.rate.setCurrentIndex(3)
        self.level=self.spin(0,1,.65,.05);self.send=self.spin(0,.8,.18,.02)
        for label,widget in [('Root note',self.pitch),('Length (s)',self.decay),('Wobble',self.rate),('Level',self.level),('Delay',self.send)]:
            top.addWidget(W.QLabel(label));top.addWidget(widget)
        area=W.QScrollArea();area.setWidgetResizable(True);layout.addWidget(area,1);body=W.QWidget();area.setWidget(body);stack=W.QVBoxLayout(body)
        for i,(title,kind,gain) in enumerate([('SUB','Sub sine',.55),('BODY','Growl',.65),('TEXTURE','Scratch',.2)]):
            group=W.QGroupBox(title);stack.addWidget(group);g=W.QGridLayout(group)
            enabled=W.QCheckBox('Layer on');enabled.setChecked(True);g.addWidget(enabled,0,0)
            engine=W.QComboBox();engine.addItems(KINDS);engine.setCurrentText(kind);g.addWidget(engine,0,1,1,3)
            row={'enabled':enabled,'kind':engine}
            specs=[('Mix','gain',0,1,gain,.05),('Transpose','transpose',-24,24,0,1),('Pan','pan',-1,1,0,.1),('Tone','tone',0,1,.5,.05),('Motion','motion',0,1,.75,.05),('Drive','drive',0,1,.4,.05),('FM ratio','ratio',.25,8,2,.25),('Pitch sweep','sweep',-36,36,12,1),('Texture','texture',0,1,.5,.05)]
            for j,(label,key,lo,hi,value,step) in enumerate(specs):
                r=1+(j//5)*2;c=j%5;g.addWidget(W.QLabel(label),r,c);sp=self.spin(lo,hi,value,step);g.addWidget(sp,r+1,c);row[key]=sp
            self.rows.append(row);engine.currentTextChanged.connect(lambda _,i=i:self.enable_controls(i));self.enable_controls(i)
        stack.addStretch()
        buttons=W.QHBoxLayout();layout.addLayout(buttons)
        for text,fn in [('Load selected lane into Forge',self.load_current),('Apply to lane',self.apply),('Apply + play',self.audition),('Save instrument',self.save),('Export patch',self.export_patch),('Import patch',self.import_patch)]:
            b=W.QPushButton(text);b.clicked.connect(fn);buttons.addWidget(b)
        self.info=W.QLabel('Draft edits take effect after Apply. Motion uses tempo-synced modulation; pitch sweeps use the selected engine’s contour.');self.info.setWordWrap(True);layout.addWidget(self.info)
    def spin(self,lo,hi,value,step):
        sp=W.QDoubleSpinBox();sp.setRange(lo,hi);sp.setSingleStep(step);sp.setValue(value);return sp
    def enable_controls(self,i):
        r=self.rows[i];kind=r['kind'].currentText()
        for key,kinds in [('ratio',('Weeewhaa','Bubble','Neuro')),('sweep',('Weeewhaa','Bubble')),('texture',('Rubber wub','Scratch','Weeewhaa','Bubble','Neuro'))]:r[key].setEnabled(kind in kinds)
        for key in ('tone','motion'):r[key].setEnabled(kind!='Sub sine')
    def patch(self):
        layers=[]
        for r in self.rows:
            data={k:w.value() for k,w in r.items() if k not in ('enabled','kind')}
            data.update(kind=r['kind'].currentText(),enabled=r['enabled'].isChecked());layers.append(data)
        if not any(d['enabled'] and d['gain']>0 for d in layers):raise ValueError('Enable at least one layer with Mix above zero.')
        p=Patch(kind='Growl',name=self.name.text().strip() or 'Custom instrument',layers=layers,note=self.pitch.value(),decay=self.decay.value(),rate=RATES[self.rate.currentIndex()],level=self.level.value(),send=self.send.value())
        state=self.win.e.state();state['patches'][0]=asdict(p);validate_state(state);return p
    def apply(self):
        try:
            p=self.patch();i=self.target.currentIndex();self.win.e.patches[i]=p;self.win.select(i)
            self.info.setText(f'{p.name} applied to lane {i+1}.');return True
        except Exception as exc:self.info.setText(str(exc));return False
    def audition(self):
        if self.apply():self.win.e.trigger(self.target.currentIndex())
    def save(self):
        if self.apply():self.win.instruments.save()
    def fill(self,p):
        self.name.setText(p.name or p.kind);self.pitch.setValue(p.note);self.decay.setValue(p.decay);self.level.setValue(p.level);self.send.setValue(p.send)
        self.rate.setCurrentIndex(min(range(len(RATES)),key=lambda i:abs(RATES[i]-p.rate)))
        layers=p.layers or [dict(kind=p.kind,enabled=True,gain=1,transpose=0,pan=p.pan,**{k:getattr(p,k) for k in ('tone','motion','drive','ratio','sweep','texture')})]
        for i,r in enumerate(self.rows):
            d=layers[i] if i<len(layers) else {'kind':'Sub sine','enabled':False,'gain':0}
            r['enabled'].setChecked(d.get('enabled',True));r['kind'].setCurrentText(d['kind'])
            defaults={'gain':.5,'transpose':0,'pan':0,'tone':.5,'motion':.75,'drive':.4,'ratio':2,'sweep':12,'texture':.5}
            for k,v in defaults.items():r[k].setValue(d.get(k,v))
            self.enable_controls(i)
    def load_current(self):
        self.target.setCurrentIndex(self.win.selected);self.fill(self.win.e.patches[self.win.selected]);self.info.setText('Selected voice loaded as an editable draft.')
    def export_patch(self):
        try:
            data={'format':'oceanboiler.patch','version':1,'patch':asdict(self.patch())}
            path,_=W.QFileDialog.getSaveFileName(self,'Export instrument','oceanboiler-patch.json','Patch (*.json)')
            if path:Path(path).write_text(json.dumps(data,indent=2));self.info.setText('Patch exported.')
        except Exception as exc:self.info.setText('Export failed: '+str(exc))
    def import_patch(self):
        path,_=W.QFileDialog.getOpenFileName(self,'Import instrument','','Patch (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>1024*1024:raise ValueError('Patch exceeds 1 MiB')
            data=json.loads(Path(path).read_text())
            if data.get('format')!='oceanboiler.patch' or data.get('version')!=1:raise ValueError('Unsupported patch format')
            state=self.win.e.state();state['patches'][0]=data['patch'];validate_state(state)
            self.fill(Patch(**data['patch']));self.info.setText('Imported into draft. Apply to assign it to a lane.')
        except Exception as exc:self.info.setText('Import failed: '+str(exc))
