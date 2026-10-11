"""Instrument browser and six physical-input assignments, separate from sound lanes."""
import json
from dataclasses import asdict
from pathlib import Path
from PySide6 import QtWidgets as W, QtCore as C
from engine import Patch, validate_state
from presets import factory_presets

class InstrumentPanel(W.QWidget):
    def __init__(self, window, config):
        super().__init__();self.win=window;self.config=config;self.factory=factory_presets();self.custom=[]
        self.path=config/'user-presets.json'
        if self.path.exists():
            try:
                custom=json.loads(self.path.read_text())
                for p in custom:
                    state=window.e.state();state['patches'][0]=p['patch'];validate_state(state)
                    if not all(isinstance(p.get(k),str) for k in ('name','category','description')):raise ValueError('Invalid preset metadata')
                self.custom=custom
            except Exception: self.load_warning='User preset file could not be read; it will not be overwritten.'
        layout=W.QHBoxLayout(self);left=W.QVBoxLayout();layout.addLayout(left,2)
        row=W.QHBoxLayout();left.addLayout(row);self.search=W.QLineEdit();self.search.setPlaceholderText('Search 52 patches: scratch, vowel, wub…');row.addWidget(self.search)
        self.family=W.QComboBox();self.family.addItems(['All']+sorted({p['category'] for p in self.factory})+['User']);row.addWidget(self.family)
        self.list=W.QListWidget();left.addWidget(self.list);self.list.setMinimumHeight(130)
        right=W.QVBoxLayout();layout.addLayout(right,1);self.detail=W.QLabel('');self.detail.setWordWrap(True);right.addWidget(self.detail)
        for text,fn in [('Load to selected lane',self.load),('Load + play',self.audition),('Save selected sound as preset',self.save)]:
            b=W.QPushButton(text);b.clicked.connect(fn);right.addWidget(b)
        right.addStretch();self.search.textChanged.connect(self.refresh);self.family.currentTextChanged.connect(self.refresh)
        self.list.currentRowChanged.connect(self.describe);self.list.itemDoubleClicked.connect(lambda _:self.audition());self.refresh()
    def refresh(self):
        q=self.search.text().lower();cat=self.family.currentText()
        self.visible=[p for p in self.factory+self.custom if (cat=='All' or p['category']==cat) and q in (p['name']+' '+p['patch']['kind']+' '+p['description']).lower()]
        self.list.clear()
        for p in self.visible:self.list.addItem(f"{p['name']}  /  {p['patch']['kind']}")
        self.list.setCurrentRow(0)
    def describe(self,index):
        self.detail.setText(self.visible[index]['description']+'\n\nLoads into the selected software lane; hardware assignments stay the same.' if 0<=index<len(self.visible) else 'No matching presets.')
    def load(self):
        i=self.list.currentRow()
        if i<0:return False
        p=self.visible[i];lane=self.win.selected
        self.win.e.patches[lane]=Patch(**p['patch']);self.win.select(lane);self.win.tell(f"{p['name']} loaded into lane {lane+1}.");return True
    def audition(self):
        if self.load():self.win.e.trigger(self.win.selected)
    def save(self):
        if hasattr(self,'load_warning'):self.win.tell(self.load_warning);return
        name,ok=W.QInputDialog.getText(self,'Save sound','Preset name:')
        if not ok or not name.strip():return
        name=name.strip();existing={p['name'] for p in self.factory+self.custom}
        base=name;i=2
        while name in existing:name=f'{base} ({i})';i+=1
        updated=self.custom+[dict(name=name,category='User',description='Your saved patch.',patch=asdict(self.win.e.patches[self.win.selected]))]
        try:
            self.config.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(updated,indent=2));temp.replace(self.path)
            self.custom=updated;self.family.setCurrentText('User');self.search.clear();self.refresh();self.win.tell('Preset saved: '+name)
        except Exception as exc:self.win.tell('Preset save failed: '+str(exc))

class HardwarePanel(W.QWidget):
    LABELS=['Pad 1','Pad 2','Pad 3','Pad 4','Kick trigger','Hi-hat controller*']
    def __init__(self,window):
        super().__init__();self.win=window;self.pending=None;self.rows=[];self.busy=False
        self.notes=[-1]*6;self.targets=list(range(6))
        layout=W.QGridLayout(self)
        for i,name in enumerate(self.LABELS):
            row=i%3;col=(i//3)*4
            layout.addWidget(W.QLabel(name),row,col)
            note=W.QSpinBox();note.setRange(-1,127);note.setSpecialValueText('Unlearned');note.setValue(-1);note.setPrefix('Note ');layout.addWidget(note,row,col+1)
            target=W.QComboBox();target.addItems([f'Lane {n+1}' for n in range(8)]);target.setCurrentIndex(i);layout.addWidget(target,row,col+2)
            learn=W.QPushButton('Learn');learn.clicked.connect(lambda _,i=i:self.learn(i));layout.addWidget(learn,row,col+3)
            self.rows.append((note,target));note.valueChanged.connect(lambda _,i=i:self.change(i));target.currentIndexChanged.connect(lambda _,i=i:self.change(i))
        explanation=W.QLabel('6 physical connections → 8 software sound lanes. *Hi-hat normally controls an H1/H2 pad; learn an emitted note only if the monitor shows one. CC-only events are monitored, not mapped to a strike.');explanation.setWordWrap(True);layout.addWidget(explanation,3,0,1,8)
    def learn(self,i):
        self.win.cancel_learn();self.pending=i;self.win.router.learn=self.targets[i];self.win.router.learn_source=True
        self.win.tell('Learning '+self.LABELS[i]+': strike/operate it. If no note is emitted, cancel; no pedal note is assumed.')
    def change(self,i):
        if self.busy:return
        note,target=self.rows[i];n=note.value();lane=target.currentIndex()
        if n>=0 and any(n==v for j,v in enumerate(self.notes) if j!=i):
            self.win.tell('This MIDI note is already assigned to another physical input.');self.refresh();return
        mapping=dict(self.win.router.mapping);old=self.notes[i]
        if old>=0 and mapping.get(old)==self.targets[i]:mapping.pop(old,None)
        if n>=0:mapping[n]=lane
        self.notes[i]=n;self.targets[i]=lane;self.win.router.mapping=mapping
        self.win.update_labels()
    def learned(self,note,lane):
        if self.pending is None:return
        i=self.pending;self.pending=None;self.rows[i][0].setValue(note)
        # setValue emits nothing if the learned note is unchanged.
        self.change(i);self.win.router.learn_source=False
    def refresh(self):
        self.busy=True
        for i,(note,target) in enumerate(self.rows):note.setValue(self.notes[i]);target.setCurrentIndex(self.targets[i])
        self.busy=False
    def reconcile(self):
        mapping=self.win.router.mapping
        for i,n in enumerate(self.notes):
            if n>=0:
                if n in mapping:self.targets[i]=mapping[n]
                else:self.notes[i]=-1
        self.refresh()
    def state(self):return dict(notes=self.notes[:],targets=self.targets[:])
    def restore(self,data):
        self.notes=data.get('notes',[-1]*6)[:];self.targets=data.get('targets',list(range(6)))[:];self.pending=None;self.refresh()
    @staticmethod
    def validate(data):
        notes=data.get('notes',[-1]*6);targets=data.get('targets',list(range(6)))
        if len(notes)!=6 or len(targets)!=6:raise ValueError('Expected six hardware assignments')
        if any(type(n)!=int or not -1<=n<=127 for n in notes):raise ValueError('Invalid hardware note')
        if any(type(n)!=int or not 0<=n<8 for n in targets):raise ValueError('Invalid target lane')
        assigned=[n for n in notes if n>=0]
        if len(assigned)!=len(set(assigned)):raise ValueError('Duplicate hardware notes')
