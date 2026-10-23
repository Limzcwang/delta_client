import unittest
from core.diagnostics import DiagnosticsBuffer
class T(unittest.TestCase):
 def test_ring_and_batch(self):
  d=DiagnosticsBuffer("0.2.12",max_events=3)
  for i in range(5): d.record("event",{"i":i})
  self.assertEqual(3,len(d.events))
  b=d.batch(); self.assertEqual(b["client_diag_id"],d.client_diag_id); self.assertEqual(3,len(b["events"])); self.assertEqual(0,len(d.events))
 def test_split_batches_512k_and_gzip(self):
  import json,gzip
  d=DiagnosticsBuffer("0.2.12")
  events=[{"kind":"tick","payload":{"blob":"x"*20000,"i":i}} for i in range(100)]
  batches=d.split_batches(events)
  self.assertGreater(len(batches),1)
  for b in batches:
   self.assertLessEqual(len(json.dumps(b,ensure_ascii=False).encode()),512*1024)
  gz=d.split_batches(events,gzip_enabled=True)
  for b in gz:
   self.assertLessEqual(len(gzip.compress(json.dumps(b,ensure_ascii=False).encode(),6)),128*1024)
 def test_redact_exe(self):
  from ui.main_window import MainWindow
  self.assertEqual(r"D:\…\DeltaForceClient-Win64-Shipping.exe", MainWindow._redact_exe(r"D:\Games\Delta\DeltaForceClient-Win64-Shipping.exe"))
 def test_batch_limit(self):
  d=DiagnosticsBuffer("0.2.12")
  for i in range(10000): d.record("tick",{"blob":"x"*200,"i":i})
  b=d.batch(); self.assertLessEqual(len(b["events"]),2000)
 def test_env_fields(self):
  d=DiagnosticsBuffer("0.2.12"); d.record("env",{"client_version":"0.2.12","os":"win32"}); b=d.batch(); self.assertEqual("0.2.12",b["client_version"]); self.assertEqual("env",b["events"][0]["kind"])
if __name__=="__main__": unittest.main()
