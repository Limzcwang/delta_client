import unittest
from core.match_flow import *
class T(unittest.TestCase):
 def test_windows(self):
  for interval,attempts,threshold in ((2000,3,1),(1000,6,3),(500,12,6)):
   w=HitWindow(interval); self.assertEqual(attempts,w.attempts); self.assertEqual(threshold,w.threshold)
 def test_early_hit(self):
  w=HitWindow(2000); self.assertEqual("hit",w.record(True))
 def test_early_abort(self):
  w=HitWindow(1000)
  for _ in range(3): self.assertEqual("continue",w.record(False))
  self.assertEqual("abort",w.record(False))
 def test_rearm_interval(self):
  w=HitWindow(2000); w.record(False); w.record(False); self.assertEqual("abort",w.record(False))
  w2=HitWindow(2000); w2.record(False); w2.rearm(500); self.assertGreater(w2.attempts,3)
 def test_parse_settlement(self):
  self.assertTrue(parse_settlement_texts(["对局时长","00:29:50","对局时间","07-31 02:09"]))
  self.assertFalse(parse_settlement_texts(["聊天"]))
  self.assertTrue(parse_countdown("29:58"))
 def test_machine_reset_share(self):
  m=MatchStateMachine(); m.set_context(logged_in=True,in_room=True); self.assertEqual(MatchPhase.OFF,m.phase)
  m.set_sharing(True); self.assertEqual(MatchPhase.IDLE,m.phase); m.reset(); self.assertEqual(MatchPhase.RUNNING,m.phase)
  m.set_sharing(False); self.assertEqual(MatchPhase.OFF,m.phase)
 def test_machine_async_stale(self):
  m=MatchStateMachine(); m.set_context(logged_in=True,in_room=True); m.set_sharing(True); m.reset(); g=m.begin_end(); self.assertEqual("continue",m.observe_end(False,generation=g)); g2=m.begin_end(); self.assertEqual("stale",m.observe_end(True,generation=g)); self.assertEqual("continue",m.observe_end(False,generation=g2))
 def test_terminate_idempotent(self):
  m=MatchStateMachine(); m.terminate(); m.terminate(); self.assertEqual(MatchPhase.OFF,m.phase)
  m.set_context(logged_in=True,in_room=True); m.set_sharing(True); m.reset(); m.terminate(); m.terminate(); self.assertEqual(MatchPhase.IDLE,m.phase)
 def test_terminate_after_end(self):
  m=MatchStateMachine(); m.set_context(logged_in=True,in_room=True); m.set_sharing(True); m.reset(); g=m.begin_end(); self.assertEqual("continue",m.observe_end(False,generation=g)); m.terminate(); self.assertEqual(MatchPhase.IDLE,m.phase); self.assertFalse(m.async_pending)
if __name__=="__main__": unittest.main()
