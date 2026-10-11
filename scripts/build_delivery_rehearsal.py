"""Build a timed presentation rehearsal from real slides, local TTS and the browser demo."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],text=True).strip())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--limit-seconds',type=float,default=600)
    p.add_argument('--playback-check',action='store_true')
    args=p.parse_args()
    build=ROOT/'.runtime/delivery-rehearsal';build.mkdir(parents=True,exist_ok=True)
    slides=ROOT/'.runtime/delivery-slides'
    data=json.loads((slides/'slide-source.json').read_text())
    parts=[];timeline=[];offset=0.0
    def run(command):subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for i,slide in enumerate(data):
        source=build/f'notes-{i+1:02}.txt';source.write_text(slide['notes'].split('Source:')[0].split('Источник:')[0])
        voice=build/f'voice-{i+1:02}.aiff'
        run(['say','-v','Milena','-r','175','-f',str(source),'-o',str(voice)])
        seconds=duration(voice)+.7
        movie=build/f'slide-{i+1:02}.mp4'
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',str(slides/f'slide-{i+1:02}.png'),'-i',str(voice),'-t',str(seconds),'-vf','scale=1280:720,setsar=1','-r','25','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(movie)])
        parts.append(movie);timeline.append({'kind':'slide','slide':i+1,'title':slide['title'],'start_seconds':offset,'duration_seconds':seconds});offset+=seconds
        if i==3:
            demo=ROOT/'doc/delivery/assets/current-demo.mp4';seconds=duration(demo)
            movie=build/'browser-demo.mp4'
            run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(demo),'-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000','-t',str(seconds),'-vf','scale=1280:720,setsar=1','-r','25','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(movie)])
            parts.append(movie);timeline.append({'kind':'actual browser demo','start_seconds':offset,'duration_seconds':seconds});offset+=seconds
    source=build/'concat.txt';source.write_text(''.join("file '"+str(path).replace("'","'\\''")+"'\n" for path in parts))
    output=ROOT/'doc/delivery/assets/timed-rehearsal.mp4'
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(source),'-c','copy','-movflags','+faststart',str(output)])
    total=duration(output)
    run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(output),'-f','null','-'])
    report={'task':'DEL-001','status':'PASS' if total<=args.limit_seconds else 'FAIL','kind':'automated timed presentation rehearsal; local synthetic speech, real browser recording','voice':'Milena local macOS TTS, 175 words/minute','code_commit':'34942b532e0ad1643db37e957ccfec30f6d77a6b','limit_seconds':args.limit_seconds,'limit_source':'working 10-minute slot from existing presentation (9-10 minutes); official organizer timing not supplied','actual_media_seconds':total,'timeline':timeline,'complete_decode':'PASS','human_presenter_run':'NOT_RUN','realtime_playback':'NOT_RUN'}
    (build/'rehearsal.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if report['status']!='PASS':raise RuntimeError('Actual rehearsal exceeds the selected slot')
    if args.playback_check:
        start=time.monotonic()
        run(['ffmpeg','-hide_banner','-loglevel','error','-re','-i',str(output),'-f','null','-'])
        elapsed=time.monotonic()-start
        assert elapsed>=total*.97,'Playback did not run in real time'
        report['realtime_playback']={'status':'PASS','elapsed_seconds':elapsed}
        (build/'rehearsal.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','actual_media_seconds','limit_seconds','realtime_playback']},ensure_ascii=False))


if __name__=='__main__':main()
