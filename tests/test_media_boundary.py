"""Real FFmpeg decoding boundaries; temporary generated clips contain no private media."""
import tempfile
import threading
import unittest
import subprocess
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mobile_backend import normalize_video,MEDIA_TOOLS,ApiError,SAFE_MEDIA_FLAGS,MOV_MEDIA_FLAGS

class MediaBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def generate(self,name,codec):
        path=self.root/name
        process=subprocess.run([str(MEDIA_TOOLS/'ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i',
             'color=c=black:s=96x96:r=12:d=1','-c:v',codec,'-y',str(path)],capture_output=True,timeout=15)
        self.assertEqual(process.returncode,0,process.stderr.decode())
        return path
    def test_mp4_mov_webm_still_normalize(self):
        for name,codec in (('input.mp4','libx264'),('input.mov','libx264'),('input.webm','libvpx-vp9')):
            with self.subTest(name=name):
                source=self.generate(name,codec);target=self.root/(name+'.normalized.mp4')
                normalize_video(source,target);self.assertGreater(target.stat().st_size,100)
    def test_hls_cannot_fetch_http_segment(self):
        hits=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                hits.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'not media')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            source=self.root/'disguised.mp4'
            source.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1.0,\nhttp://127.0.0.1:'+str(server.server_port)+'/private.ts\n#EXT-X-ENDLIST\n')
            with self.assertRaises(ApiError):normalize_video(source,self.root/'out.mp4')
            self.assertEqual(hits,[])
        finally:server.shutdown();server.server_close()
    def test_concat_and_local_playlists_are_not_demuxed(self):
        actual=self.generate('local.mp4','libx264')
        for name,text in (('concat.mp4',"ffconcat version 1.0\nfile '"+str(actual)+"'\n"),
                          ('local-hls.mp4','#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1.0,\n'+str(actual)+'\n#EXT-X-ENDLIST\n')):
            source=self.root/name;source.write_text(text)
            with self.assertRaises(ApiError):normalize_video(source,self.root/(name+'.out.mp4'))
        self.assertIn('mov,matroska,webm',SAFE_MEDIA_FLAGS)
        self.assertEqual(MOV_MEDIA_FLAGS,['-enable_drefs','0'])
    def test_llm_retries_only_invalid_format_once(self):
        from unittest.mock import patch
        import intent
        valid={'kind':'shorten','minutes':30,'discomfort':False}
        with patch.object(intent,'_extract',side_effect=[ValueError('invalid'),valid]) as fn:
            self.assertEqual(intent._extract_validated(None,'input'),(valid,2));self.assertEqual(fn.call_count,2)
        with patch.object(intent,'_extract',return_value=None) as fn:
            self.assertEqual(intent._extract_validated(None,'input'),(None,2));self.assertEqual(fn.call_count,2)
        with patch.object(intent,'_extract',side_effect=TimeoutError('timeout')) as fn:
            with self.assertRaises(TimeoutError):intent._extract_validated(None,'input')
            self.assertEqual(fn.call_count,1)

if __name__=='__main__':unittest.main()
