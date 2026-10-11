"""52 original synthesis patches; no copied artist presets or external samples."""
from dataclasses import asdict
from engine import Patch

FAMILIES = {
 'Growl': ('Bass', 'FM throat with moving resonant low-pass and sub.', ['Swamp jaw','Gravel maw','Ritual growl','Iron throat']),
 'Talking bass': ('Vowels', 'Two moving formants over FM excitation.', ['Yah beast','Ooh cavern','Alien vowel','Wah sermon']),
 'Reese': ('Bass', 'Detuned harmonic banks with a stable sub.', ['Deep drift','Split coil','Black current','Wide pressure']),
 'Sub drop': ('Sub', 'Pitch fall into a smooth low fundamental.', ['Floor sink','Gravity well','Low tide','Tunnel drop']),
 'Kick': ('Drums', 'Pitch-envelope kick with filtered transient.', ['Heavy boot','Round thump','Dry punch','Dungeon kick']),
 'Snare': ('Drums', 'Tuned snare body and noise snap.', ['Ritual clap','Dust snare','Steel smack','Canyon snap']),
 'Hat': ('Drums', 'Noise and metallic partials.', ['Sand hat','Tight tick','Rust shaker','Air cutter']),
 'Metal': ('FX', 'Inharmonic FM resonator.', ['Alien bell','Scrap gong','Wire sting','Ritual plate']),
 'Rubber wub': ('Wubs', 'Resonant filter sweep over a harmonic oscillator.', ['Rubber room','Elastic stomp','Jelly wobble','Tire monster']),
 'Scratch': ('Scratches', 'Forward/reverse interpolated procedural tape; no samples.', ['Crab swipe','Gravel scratch','Vinyl beast','Reverse rip']),
 'Weeewhaa': ('Sweeps', 'Rising/falling pitch against an opposing filter contour.', ['Weeewhaa','Whale call','Portal bend','Reverse siren']),
 'Bubble': ('FX', 'Short pitch-envelope FM bubbles and zaps.', ['Bog bubble','Laser droplet','Plasma gulp','Water zap']),
 'Neuro': ('Bass', 'Nested FM and moving spectral cancellation.', ['Nerve coil','Serrated pulse','Feral circuit','Liquid wire']),
}

def factory_presets():
    out=[]
    for family,(category,description,names) in FAMILIES.items():
        for i,name in enumerate(names):
            duration={'Kick':.5,'Snare':.32,'Hat':.12,'Metal':.8,'Bubble':.6,'Scratch':.9}.get(family,1.5)
            p=Patch(kind=family,note=[29,26,31,24][i],decay=duration*[1,.7,1.3,1.65][i],
                    tone=[.45,.25,.75,.6][i],motion=[.7,.95,.55,1][i],drive=[.45,.65,.8,.55][i],
                    rate=[2,1,3,4][i],send=[.16,.28,.1,.36][i],ratio=[2,1.5,3.7,.5][i],
                    sweep=[12,24,7,-24][i],texture=[.35,.65,.85,.5][i])
            if family=='Hat':p.level=.35
            if family=='Kick':p.send=0;p.level=.8
            out.append(dict(name=name,category=category,description=description,patch=asdict(p)))
    return out
