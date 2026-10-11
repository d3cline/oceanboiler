import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
import time
import json
import tempfile
import numpy as np
import mido
from engine import Engine, Voice, Patch, KINDS, kit, validate_state
from io_layer import MidiRouter, Recorder

class EngineTests(unittest.TestCase):
    def test_all_engines_and_extremes(self):
        for kind in KINDS:
            for tone in (0.,1.):
                e=Engine();e.patches[0]=Patch(kind=kind,tone=tone,drive=1,motion=1,decay=.12)
                e.trigger(0,127)
                a=np.concatenate([e.render(256) for _ in range(35)])
                self.assertTrue(np.isfinite(a).all(),kind)
                self.assertGreater(np.max(np.abs(a)),.005,kind)
                self.assertLessEqual(np.max(np.abs(a)),.941,kind)
                self.assertEqual(len(e.voices),0)
    def test_midi_ktmp1(self):
        e=Engine();r=MidiRouter(e);r.learn=0
        r.receive(mido.Message('note_on',channel=9,note=38,velocity=90))
        e.handle();self.assertEqual(len(e.voices),1);self.assertEqual(r.mapping,{38:0})
        r.receive(mido.Message('note_on',channel=9,note=38,velocity=0));e.handle()
        self.assertEqual(len(e.voices),1,'zero velocity must never retrigger')
        r.receive(mido.Message('note_off',channel=9,note=38,velocity=80));e.handle()
        self.assertEqual(len(e.voices),1,'one shots must ignore early note off')
        r.receive(mido.Message('note_on',channel=0,note=38,velocity=90));e.handle();self.assertEqual(len(e.voices),1)
        r.learn=1;r.receive(mido.Message('note_on',channel=9,note=38,velocity=90));self.assertEqual(r.learn,1)
        self.assertEqual(r.mapping,{38:0})
    def test_sequence_timing(self):
        e=Engine();e.bpm=120;e.swing=.3;e.steps=[[0]*32 for _ in range(8)];e.commands.put(('play',True))
        e.render(48000);self.assertEqual(e.step,7);self.assertAlmostEqual(e.until_step,0,places=4)
        e.render(1);self.assertEqual(e.step,8)
    def test_panic_and_polyphony(self):
        e=Engine()
        for i in range(100):e.trigger(i%8)
        e.render(256);self.assertLessEqual(len(e.voices),32)
        e.commands.put(('panic',));a=e.render(256);self.assertEqual(float(np.max(abs(a))),0)
    def test_session_validation(self):
        e=Engine();s=json.loads(json.dumps(e.state()));validate_state(s)
        e.commands.put(('session',s));e.handle();self.assertEqual(e.state(),s)
        s['feedback']=float('nan')
        with self.assertRaises(ValueError):validate_state(s)
    def test_preset_bank_and_old_sessions(self):
        from presets import factory_presets
        presets=factory_presets();self.assertEqual(len(presets),52)
        for item in presets:
            e=Engine();state=e.state();state['patches'][0]=item['patch'];validate_state(state)
            e.patches[0]=Patch(**item['patch']);e.trigger(0)
            a=np.concatenate([e.render(256) for _ in range(12)])
            self.assertTrue(np.isfinite(a).all(),item['name'])
            self.assertGreater(np.max(np.abs(a)),.0001,item['name'])
        old=Engine().state()
        for p in old['patches']:
            for key in ('ratio','sweep','texture'):p.pop(key)
        validate_state(old);e=Engine();e.commands.put(('session',old));e.render(256)
        self.assertEqual(e.patches[0].ratio,2)
    def test_record(self):
        import soundfile as sf
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'take.wav');r=Recorder(path,48000)
            for _ in range(4):r.push(np.zeros((256,2),dtype=np.float32))
            r.close();info=sf.info(path);self.assertEqual(info.frames,1024);self.assertEqual(info.subtype,'PCM_24');self.assertFalse(r.error)

if __name__=='__main__':unittest.main()
