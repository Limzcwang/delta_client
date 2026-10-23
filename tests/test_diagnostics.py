import unittest
from core.diagnostics import DiagnosticsBuffer
class T(unittest.TestCase):
 def test_ring_and_batch(self):
  d=DiagnosticsBuffer("0.2.12",max_events=3)
  for i in range(5): d.record("event",{"i":i})
  self.assertEqual(3,len(d.events))
  b=d.batch(); self.assertEqual(b["client_diag_id"],d.client_diag_id); self.assertEqual(3,len(b["events"])); self.assertEqual(0,len(d.events))
 def test_env_fields(self):
  d=DiagnosticsBuffer("0.2.12"); d.record("env",{"client_version":"0.2.12","os":"win32"}); b=d.batch(); self.assertEqual("0.2.12",b["client_version"]); self.assertEqual("env",b["events"][0]["kind"])
if __name__=="__main__": unittest.main()
