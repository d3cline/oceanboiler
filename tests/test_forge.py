import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from engine import Engine,Patch,validate_state

class ForgeTests(unittest.TestCase):
    def test_layered_voice_roundtrip_and_cleanup(self):
        e=Engine();e.patches[0]=Patch(name='Test boiler',decay=.15,layers=[
            dict(kind='Sub sine',gain=.5),dict(kind='Neuro',gain=.6,ratio=3),dict(kind='Scratch',gain=.2)])
        state=json.loads(json.dumps(e.state()));validate_state(state)
        e.commands.put(('session',state));e.trigger(0)
        a=np.concatenate([e.render(256) for _ in range(70)])
        self.assertTrue(np.isfinite(a).all());self.assertGreater(abs(a).max(),.01)
        self.assertLess(abs(a).max(),.95);self.assertEqual(len(e.voices),0)
        self.assertEqual(e.patches[0].name,'Test boiler');self.assertEqual(len(e.patches[0].layers),3)
    def test_reject_recursive_or_invalid_layers(self):
        for layers in [[{'kind':'Growl','layers':[]}],[{'kind':'Sub sine','gain':float('nan')}],[{'kind':'Growl'}]*4]:
            s=Engine().state();s['patches'][0]['layers']=layers
            with self.assertRaises(ValueError):validate_state(s)
    def test_disabled_layer_is_silent(self):
        e=Engine();e.patches[0]=Patch(layers=[dict(kind='Growl',enabled=False)])
        e.trigger(0);self.assertEqual(abs(e.render(256)).max(),0)

if __name__=='__main__':unittest.main()
