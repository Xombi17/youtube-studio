"""Structural checks for an authored plan. This does not certify visual quality."""
import argparse,json
from pathlib import Path

def validate(plan,presets):
    errors=[];warnings=[]
    def need(ok,message):
        if not ok:errors.append(message)
    d=plan.get('duration_seconds',0);words=plan.get('script_word_count',0)
    canvas=plan.get('canvas',{})
    need((canvas.get('width'),canvas.get('height'),canvas.get('fps'))==(1080,1920,30),'Delivery must be 1080x1920 at 30 fps.')
    need(28<=d<=45,'Duration must be 28–45 seconds.')
    wpm=words/d*60 if d else 0
    need(165<=wpm<=180,'Narration must be 165–180 WPM.')
    if d>=30:need(85<=words<=135,'For a 30–45s film, use 85–135 words.')
    need(plan.get('voice_onset_seconds',99)<=.05,'Voice onset exceeds 0.05s.')
    need(plan.get('voice_tail_seconds',99)<=.10,'Voice tail exceeds 0.10s.')
    need(plan.get('first_2_5s_spoken_words',99)<=10,'More than ten words in first 2.5s.')
    clocks=plan.get('clocks',{})
    need(clocks=={'paper_poses':12,'camera_world':30,'type_captions':30},'Keep 12fps paper poses separate from 30fps camera/world/type.')
    gaps=plan.get('inter_beat_gaps_seconds',[])
    need(bool(gaps),'Measured inter-beat gaps are required.')
    need(sum(.18<=g<=.24 for g in gaps)<=1,'Only one dramatic pause is allowed.')
    need(all(.06<=g<=.12 or .18<=g<=.24 for g in gaps),'An inter-beat gap is outside the permitted range.')
    hooks=plan.get('rehook_times',[])
    previous=0
    for t in hooks:
        need(10<=t-previous<=12,'Re-hooks must be 10–12s apart, including the opening interval.');previous=t
    need(bool(hooks) and d-previous<=12,'The final stretch after the last re-hook exceeds 12s.')
    def in_box(b,outer):
        return isinstance(b,list) and len(b)==4 and b[0]<b[2] and b[1]<b[3] and b[0]>=outer[0] and b[1]>=outer[1] and b[2]<=outer[2] and b[3]<=outer[3]
    need(in_box(plan.get('caption_rect'),[60,200,910,1350]),'Caption rectangle enters a forbidden UI zone.')
    need(plan.get('template_chrome') is False,'Template chrome must be disabled.')
    events=plan.get('events',[]);times=[e.get('time',-1) for e in events]
    need(bool(times) and times[0]==0 and times==sorted(set(times)),'Visual events must start at zero and have unique ordered times.')
    intervals=[b-a for a,b in zip(times,times[1:]+[d])]
    need(bool(intervals) and all(1.2<=x<=2 for x in intervals),'Meaningful visual event spacing must be 1.2–2.0s.')
    need(all(e.get('information_change') and e.get('anchor') for e in events),'Each event needs an information change and a visual anchor.')
    available={p['id'] for p in presets['presets']}
    scenes=plan.get('scenes',[])
    need(bool(scenes),'At least one scene is required.')
    prev=0
    for s in scenes:
        need(abs(s.get('start',-99)-prev)<.002 and s.get('end',0)>s.get('start',0),'Scenes must cover the timeline without gaps or overlaps.')
        prev=s.get('end',0)
        need(in_box(s.get('critical_art_rect'),[60,220,900,1180]),'A scene hero rectangle enters a forbidden UI zone.')
        need(bool(s.get('camera_intent')) and bool(s.get('anchor')),'Each scene needs camera intent and a persistent anchor.')
        need(all(p in available for p in s.get('motion_presets',[])),'A scene references an unknown motion preset.')
    need(abs(prev-d)<.002,'Scenes must end at the delivery duration.')
    need(any(s.get('visual_proof') for s in scenes),'At least one actual mechanism/proof sequence is required.')
    if len({s.get('family') for s in scenes})<4:warnings.append('Use a broader range of presentation families or document why one continuous world is clearer.')
    need(plan.get('loop',{}).get('bridge_text') and plan.get('loop',{}).get('matched_anchor'),'The loop needs both a spoken bridge and a matched visual anchor.')
    need(plan.get('audio_handoff',{})=={'sample_rate':48000,'bit_depth':24,'stems':['dialogue','music','sfx']},'Provide 48kHz/24-bit dialogue, music and SFX stems.')
    warnings.append('Plan geometry is not rendered-frame proof. Check actual swept glyph/art bounds, blur, alpha, audio and the loop after export.')
    return {'valid':not errors,'errors':errors,'warnings':warnings,'derived_wpm':wpm,'visual_events':len(events),'scenes':len(scenes),'status':'Structural validation only; no claim that a film has been rendered or visually approved.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('plan',type=Path);ap.add_argument('--presets',type=Path);args=ap.parse_args()
    base=Path(__file__).resolve().parent.parent
    preset=args.presets or base/'presets/motion-presets.json'
    out=validate(json.loads(args.plan.read_text(encoding='utf-8')),json.loads(preset.read_text(encoding='utf-8')))
    print(json.dumps(out,indent=2));raise SystemExit(0 if out['valid'] else 1)

if __name__=='__main__':main()
