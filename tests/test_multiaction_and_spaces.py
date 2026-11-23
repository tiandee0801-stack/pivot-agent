"""Geometry invariants and actual HTTP tenant isolation, not accuracy claims."""
import http.cookiejar
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import dispatch, RequestError
from guest_spaces import GuestSpaces
from intent import LocalIntent
from mobile_backend import VideoManager
from server import PivotHandler
from video_engine.exercises import EXERCISES, counter_angle, make_counter, measure
from video_engine.vision import boxes_from_clockwise


class MultiActionTests(unittest.TestCase):
    def points(self, exercise, angle, side='left'):
        points=[[0,0,0] for _ in range(17)]
        a,b,c=[i+(side=='right') for i in EXERCISES[exercise]['indices']]
        rad=math.radians(angle)
        points[a]=[.5,.3,.99]
        points[b]=[.5,.5,.99]
        points[c]=[.5+.2*math.sin(rad),.5-.2*math.cos(rad),.99]
        if exercise=='pushup':points[11+(side=='right')]=[.8,.3,.99]
        return points

    def test_all_five_geometries_use_selected_side_and_confidence(self):
        self.assertEqual(len(EXERCISES),5)
        for exercise in EXERCISES:
            for side in ('left','right'):
                with self.subTest(exercise=exercise,side=side):
                    p=self.points(exercise,83,side)
                    self.assertAlmostEqual(measure(p,side,exercise),83)
                    self.assertIsNone(measure(p,'right' if side=='left' else 'left',exercise))
                    p[EXERCISES[exercise]['indices'][1]+(side=='right')][2]=.1
                    self.assertIsNone(measure(p,side,exercise))

    def test_complete_cycles_are_action_specific(self):
        for exercise,cfg in EXERCISES.items():
            c=make_counter(exercise)
            start,end=cfg['extended']+5,cfg['flexed']-5
            raw_start=180-start if cfg['invert'] else start
            raw_end=180-end if cfg['invert'] else end
            raw_middle=(raw_start+raw_end)/2
            sequence=[raw_start]*5+[raw_middle]*3+[raw_end]*5+[raw_middle]*3+[raw_start]*5
            for i,a in enumerate(sequence):
                angle=measure(self.points(exercise,a),'left',exercise)
                c.update(i*.125,counter_angle(angle,exercise),angle is not None)
            self.assertEqual(c.count,1,exercise)

    def test_press_does_not_use_curl_elbow_bend(self):
        self.assertEqual(EXERCISES['overhead_press']['indices'],(11,5,7))
        points=self.points('bicep_curl',60)
        self.assertIsNone(measure(points,'left','overhead_press'))

    def test_pushup_requires_visible_horizontal_torso(self):
        points=self.points('bicep_curl',60)
        points[11]=[.5,.7,.99]
        self.assertIsNone(measure(points,'left','pushup'))
        points[11]=[.9,.3,.1]
        self.assertIsNone(measure(points,'left','pushup'))
        points[11][2]=.99
        self.assertAlmostEqual(measure(points,'left','pushup'),60)

    def test_pushup_projected_cycle_can_be_observed_without_straight_180(self):
        c=make_counter('pushup')
        for i,angle in enumerate([150]*5+[130]*3+[90]*5+[130]*3+[150]*5):
            projected=measure(self.points('pushup',angle),'left','pushup')
            c.update(i*.125,projected,projected is not None)
        self.assertEqual(c.count,1)
        # A torso standing upright remains invalid despite elbow movement.
        c=make_counter('pushup')
        for i,angle in enumerate([150]*5+[90]*5+[150]*5):
            points=self.points('pushup',angle);points[11]=[.5,.8,.99]
            projected=measure(points,'left','pushup')
            c.update(i*.125,projected,projected is not None)
        self.assertEqual(c.count,0)

    def test_rotated_detection_maps_back_to_original_frame(self):
        self.assertEqual(boxes_from_clockwise([[99,10,179,110]],200),[[10.,20.,110.,100.]])

    def test_bad_geometry_never_becomes_angle(self):
        for points in ([],None,[None]*17,[[0,0,0]]*17,[[float('nan'),.1,1]]*17):
            self.assertIsNone(measure(points,'left','squat'))


class GuestSpaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.spaces=GuestSpaces(self.root/'visitors')
        self.base=VideoManager(self.root/'base.sqlite3')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(PivotHandler,
            db_path=str(self.root/'base.sqlite3'),video=self.base,model=LocalIntent(enabled=False),pairing=self.spaces))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        self.base.pool.shutdown()
        for db,manager in self.spaces.managers.values():manager.pool.shutdown()
        self.tmp.cleanup()

    def client(self):
        jar=http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)),jar

    def request(self,client,path,method='GET',body=None):
        req=urllib.request.Request(self.url+path,method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'})
        try:response=client.open(req,timeout=10)
        except urllib.error.HTTPError as exc:response=exc
        return response.status,json.loads(response.read())

    def test_open_without_code_but_each_browser_has_private_records(self):
        alice,ajar=self.client();bob,bjar=self.client()
        code,a=self.request(alice,'/api/state');self.assertEqual(code,200)
        code,b=self.request(bob,'/api/state');self.assertEqual(code,200)
        self.assertNotEqual(list(ajar)[0].value,list(bjar)[0].value)
        self.assertFalse(a['permissions']['device'])
        result=self.request(alice,'/api/sessions','POST',dict(completion='completed',minutes=18,
            feeling='合适',discomfort=False,note='only alice',idempotencyKey='alice_first_session'))
        self.assertEqual(result[0],200)
        sid=result[1]['savedSessionId']
        self.assertEqual(len(self.request(alice,'/api/state')[1]['sessions']),1)
        self.assertEqual(self.request(bob,'/api/state')[1]['sessions'],[])
        self.assertEqual(self.request(bob,'/api/sessions/'+sid,'DELETE')[0],404)
        self.assertEqual(len(self.request(alice,'/api/state')[1]['sessions']),1)
        # Knowing another space's media id grants no access.
        self.assertEqual(self.request(bob,'/api/jobs/'+'a'*32)[0],404)

    def test_invalid_space_token_is_rejected_and_cookie_clears(self):
        for token in ('','../escape','0'*47,'X'*48):
            with self.assertRaises(RequestError):self.spaces.workspace(token)
        self.assertIn('Max-Age=0',self.spaces.cookie(''))


if __name__=='__main__':unittest.main()
