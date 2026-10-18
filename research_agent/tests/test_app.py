import json,sys,threading,time,unittest,urllib.request,urllib.error,re,io,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_server
class BrowserFlowTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=create_server(0);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_port}';cls.token=cls.server.state.token
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def request(self,path,data=None,token=True,origin=None):
  h={'Content-Type':'application/json'}
  if token:h['X-Research-Token']=self.token
  if origin:h['Origin']=origin
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
  with urllib.request.urlopen(req,timeout=10) as r:return r.status,r.read()
 def test_complete_file_upload_demo_job_and_download(self):
  status,body=self.request('/');self.assertEqual(status,200);self.assertIn(b'research-token',body)
  _,body=self.request('/api/import',{'name':'paper.csv','text':'PMID,제목,영문초록\n1,논문 하나,source text\n2,초록 없음,\n'})
  ds=json.loads(body);self.assertEqual(ds['count'],2);self.assertEqual(ds['abstracts'],1)
  _,body=self.request('/api/run',{'dataset_id':ds['dataset_id'],'limit':1,'config':{'mode':'demo'}});jid=json.loads(body)['job_id']
  for _ in range(100):
   _,body=self.request('/api/job?id='+jid);job=json.loads(body)
   if job['status']!='running':break
   time.sleep(.01)
  self.assertEqual(job['status'],'done');self.assertEqual(job['summary']['not_selected'],1)
  _,body=self.request('/api/download?id='+jid+'&format=zip')
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   result=json.loads(z.read('research_results.json'));self.assertEqual(result['total_input_count'],2);self.assertEqual(result['real_model_calls'],0);self.assertIn('research_results.csv',z.namelist())
 def test_other_origin_and_missing_token_blocked(self):
  for options in [{'token':False},{'origin':'https://example.invalid'}]:
   with self.assertRaises(urllib.error.HTTPError) as c:self.request('/api/demo',{},**options)
   self.assertEqual(c.exception.code,403)
 def test_live_calls_require_explicit_checkbox_and_credentials(self):
  _,body=self.request('/api/import',{'name':'p.csv','text':'PMID,Title,Abstract\n1,A,Some abstract\n'});ds=json.loads(body)
  with self.assertRaises(urllib.error.HTTPError) as c:self.request('/api/run',{'dataset_id':ds['dataset_id'],'config':{'mode':'live'}})
  self.assertEqual(c.exception.code,400);self.assertFalse(self.server.state.jobs and any(j['mode']=='live' for j in self.server.state.jobs.values()))
if __name__=='__main__':unittest.main()
