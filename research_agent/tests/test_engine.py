import io,json,sys,threading,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine as e

class EngineTests(unittest.TestCase):
 def test_nbib_multiline_and_missing_abstract_retained(self):
  rs=e.parse_records('test.nbib','PMID- 1\nTI  - A title\n      continued\nAB  - Original source sentence long enough for validation.\nPT  - Journal Article\n\nPMID- 2\nTI  - Without abstract\n')
  self.assertEqual(len(rs),2);self.assertEqual(rs[0]['title'],'A title continued');self.assertEqual(rs[1]['abstract'],'');self.assertEqual(rs[0]['source_fields']['PT'],['Journal Article'])
 def test_korean_csv_and_duplicate_rows_kept(self):
  rs=e.parse_records('x.csv','PMID,제목,영문초록,장기태그\n1,첫 제목,first abstract,간\n1,다른 기록,,폐\n')
  self.assertEqual(len(rs),2);self.assertTrue(rs[1]['duplicate_pmid']);self.assertNotEqual(rs[0]['record_id'],rs[1]['record_id']);self.assertEqual(rs[1]['source_fields']['장기태그'],'폐')
 def test_demo_preserves_every_record_and_unselected(self):
  rs=e.demo_records();out=e.run_team(rs,[rs[0]['record_id']],{'mode':'demo'})
  self.assertEqual(len(out['records']),3);self.assertEqual(out['real_model_calls'],0);self.assertEqual(out['demo_steps'],4);self.assertEqual(out['outputs'][1]['status'],'not_selected');self.assertEqual(len(out['outputs'][0]['audit']['valid_claims']),1)
 def test_demo_does_not_fake_uploaded_article_findings(self):
  rs=e.parse_records('x.nbib','PMID- 123\nTI  - Real looking title\nAB  - Some source text of adequate length.\n')
  out=e.run_team(rs,[rs[0]['record_id']],{'mode':'demo'})
  self.assertEqual(out['outputs'][0]['supervisor']['output']['claims'],[])
 def test_quote_occurrence_pmid_and_missing_abstract(self):
  r=e.demo_records()[0];claim={'isoform':'HIF-1','organ':'uterus','function':'test','context':'synthetic','direction':'association','evidence_quote':'This fabricated phrase is not in the source.'}
  output={'pmid':'OTHER','organs':['uterus'],'claims':[claim],'uncertainties':[]}
  a=e.audit_output(r,output);self.assertFalse(a['valid_claims']);self.assertTrue(a['flagged_claims']);self.assertIn('PMID가 원본과 다릅니다.',a['issues'])
  output['pmid']=r['pmid'];claim['evidence_quote']=r['abstract'];r['abstract']='';self.assertFalse(e.audit_output(r,output)['valid_claims'])
 def test_retracted_claim_is_flagged_but_record_not_dropped(self):
  r=e.demo_records()[0];r['status']='Retracted Publication'
  result=e.DemoAdapter()('supervisor',r,{})['output'];a=e.audit_output(r,result)
  self.assertFalse(a['valid_claims']);self.assertTrue(any('철회' in x for x in a['flagged_claims'][0]['reasons']))
 def test_workers_run_independently_in_parallel_and_secret_not_serialized(self):
  barrier=threading.Barrier(3);seen={};lock=threading.Lock();secret='NEVER-SERIALIZE-TEST-KEY'
  def fake(role,record,config,workers=None):
   if role!='supervisor':
    self.assertIsNone(workers);barrier.wait(timeout=3)
   else:self.assertEqual(set(workers),{'classifier','extractor','critic'})
   with lock:seen[role]=config.get('goal')
   return e.DemoAdapter()(role,record,config,workers)
  r=e.demo_records();config={'mode':'live','goal':'custom goal','roles':{role:{'provider':'openai','key':secret,'model':'test'} for role in e.ROLES}}
  result=e.run_team(r,[r[0]['record_id']],config,adapter=fake)
  self.assertEqual(set(seen),set(e.ROLES));self.assertTrue(all(x=='custom goal' for x in seen.values()));self.assertNotIn(secret,json.dumps(result));self.assertEqual(result['real_model_calls'],4)
 def test_partial_failure_keeps_successful_outputs_and_skips_supervisor(self):
  def fake(role,record,config,workers=None):
   if role=='critic':raise e.ProviderError('HTTP 429 limit')
   if role=='supervisor':raise AssertionError('should not run')
   return e.DemoAdapter()(role,record,config)
  rs=e.demo_records();out=e.run_team(rs,[rs[0]['record_id']],{'mode':'live'},adapter=fake)
  self.assertEqual(out['outputs'][0]['status'],'worker_failed');self.assertIsNotNone(out['outputs'][0]['workers']['extractor']['output']);self.assertEqual(out['real_model_calls'],3);self.assertIn('HTTP 429',e.export_csv(out))
 def test_all_four_provider_payloads_and_auth_headers(self):
  source='Return JSON';requests=[]
  def mocked(req,timeout):
   requests.append(req);url=req.full_url
   if 'anthropic' in url:obj={'content':[{'type':'text','text':'{"ok":true}'}]}
   elif 'googleapis' in url:obj={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}]}
   else:obj={'choices':[{'message':{'content':'{"ok":true}'}}]}
   return io.BytesIO(json.dumps(obj).encode())
  with patch('engine.urllib.request.urlopen',mocked):
   for provider in e.PROVIDERS:self.assertEqual(e.call_model(provider,'SECRET','test-model','sys',source)['output'],{'ok':True})
  self.assertEqual(len(requests),4)
  for req in requests:
   self.assertNotIn('SECRET',req.full_url);body=json.loads(req.data);self.assertNotIn('SECRET',str(body))
  gemini=next(r for r in requests if 'googleapis' in r.full_url);self.assertEqual(gemini.get_header('X-goog-api-key'),'SECRET');self.assertIn('systemInstruction',json.loads(gemini.data))
  openai=next(r for r in requests if 'openai' in r.full_url);self.assertIn('max_completion_tokens',json.loads(openai.data))
 def test_provider_error_body_never_exposed(self):
  err=urllib.error.HTTPError('https://api.openai.com',401,'Bad',{},io.BytesIO(b'echo SECRET'))
  with patch('engine.urllib.request.urlopen',side_effect=err):
   with self.assertRaises(e.ProviderError) as caught:e.call_model('openai','SECRET','test','sys','user')
  self.assertNotIn('SECRET',str(caught.exception));self.assertIn('401',str(caught.exception))
 def test_non_json_provider_response_is_preserved(self):
  with patch('engine.request_json',return_value={'choices':[{'message':{'content':'not JSON'}}]}):
   result=e.call_model('deepseek','SECRET','test','sys','x')
  self.assertEqual(result['raw_text'],'not JSON');self.assertTrue(result['error']);self.assertIsNone(result['output'])
 def test_csv_formula_input_is_safe(self):
  rs=e.demo_records();rs[0]['title']='=1+1';r=e.run_team(rs,[rs[0]['record_id']],{'mode':'demo'});self.assertIn("'=1+1",e.export_csv(r))

if __name__=='__main__':unittest.main()
