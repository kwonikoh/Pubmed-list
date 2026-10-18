"""Local-only, dependency-free browser UI. Run: python app.py"""
from __future__ import annotations
import argparse,io,json,secrets,threading,urllib.parse,webbrowser,zipfile
from collections import Counter
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from engine import PROVIDERS,ROLES,parse_records,demo_records,run_team,list_models,export_csv,ProviderError
ROOT=Path(__file__).parent
MAX_BODY=64*1024*1024
class State:
 def __init__(self):self.token=secrets.token_urlsafe(32);self.datasets={};self.jobs={};self.lock=threading.Lock()

def create_server(port=8765):
 state=State()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,status,data,ctype='application/json; charset=utf-8',filename=None):
   if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode()
   elif isinstance(data,str):data=data.encode()
   self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
   self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
   if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
   self.end_headers();self.wfile.write(data)
  def authorized(self):
   allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
   if self.headers.get('Host') not in allowed:self.reply(403,{'error':'허용하지 않는 호스트입니다.'});return False
   origin=self.headers.get('Origin')
   if origin and origin not in {f'http://{a}' for a in allowed}:self.reply(403,{'error':'다른 웹사이트에서 실행할 수 없습니다.'});return False
   if self.headers.get('X-Research-Token')!=state.token:self.reply(403,{'error':'화면을 새로 열어 실행하세요.'});return False
   return True
  def do_GET(self):
   path=urllib.parse.urlsplit(self.path).path
   if path in ['/','/static/app.js','/static/style.css']:
    if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:self.reply(403,{'error':'허용하지 않는 호스트'});return
    name={'/':'index.html','/static/app.js':'app.js','/static/style.css':'style.css'}[path]
    data=(ROOT/'static'/name).read_text()
    if path=='/':data=data.replace('__TOKEN__',state.token)
    self.reply(200,data,'text/html; charset=utf-8' if path=='/' else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8');return
   if not self.authorized():return
   q=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
   if path=='/api/job':
    job=state.jobs.get(q.get('id',[''])[0])
    if not job:self.reply(404,{'error':'작업을 찾지 못했습니다.'});return
    self.reply(200,{k:v for k,v in job.items() if k!='result'});return
   if path=='/api/download':
    job=state.jobs.get(q.get('id',[''])[0]);fmt=q.get('format',['json'])[0]
    if not job or job['status']!='done':self.reply(409,{'error':'완료된 결과가 없습니다.'});return
    result=job['result']
    if fmt=='csv':self.reply(200,export_csv(result),'text/csv; charset=utf-8','research_results.csv')
    elif fmt=='zip':
     buf=io.BytesIO()
     with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
      z.writestr('research_results.json',json.dumps(result,ensure_ascii=False,indent=2));z.writestr('research_results.csv',export_csv(result))
     self.reply(200,buf.getvalue(),'application/zip','research_results.zip')
    else:self.reply(200,json.dumps(result,ensure_ascii=False,indent=2),'application/json; charset=utf-8','research_results.json')
    return
   self.reply(404,{'error':'경로가 없습니다.'})
  def do_POST(self):
   if not self.authorized():return
   try:
    length=int(self.headers.get('Content-Length','0'))
    if length<=0 or length>MAX_BODY:raise ValueError('요청은 64MB 이하 JSON이어야 합니다.')
    data=json.loads(self.rfile.read(length));path=urllib.parse.urlsplit(self.path).path
    if path=='/api/import':
     name=str(data.get('name',''));text=str(data.get('text',''))
     if len(text.encode())>40*1024*1024:raise ValueError('파일은 40MB 이하로 선택하세요.')
     records=parse_records(name,text);dataset_id=secrets.token_urlsafe(12)
     with state.lock:
      if len(state.datasets)>=3:raise ValueError('이 실행에서 파일 3개를 불러왔습니다. 앱을 다시 시작해 메모리를 비울 수 있습니다.')
      state.datasets[dataset_id]=records
     self.reply(200,{'dataset_id':dataset_id,'count':len(records),'abstracts':sum(bool(r['abstract']) for r in records),'preview':[{'pmid':r['pmid'],'title':r['title']} for r in records[:8]]});return
    if path=='/api/demo':
     dataset_id=secrets.token_urlsafe(12);state.datasets[dataset_id]=demo_records()
     self.reply(200,{'dataset_id':dataset_id,'count':3,'abstracts':2,'preview':[{'pmid':r['pmid'],'title':r['title']} for r in state.datasets[dataset_id]]});return
    if path=='/api/models':
     provider=data.get('provider');key=data.get('key','')
     if provider not in PROVIDERS:raise ValueError('제공자를 선택하세요.')
     self.reply(200,{'models':list_models(provider,key)});return
    if path=='/api/run':
     records=state.datasets.get(data.get('dataset_id',''))
     if records is None:raise ValueError('먼저 파일 또는 합성 예제를 불러오세요.')
     limit=int(data.get('limit',3))
     if not 1<=limit<=20:raise ValueError('실행 편수는 1~20으로 선택하세요.')
     query=str(data.get('query','')).casefold().strip();matching=[r for r in records if not query or query in (r['title']+' '+r['abstract']).casefold()]
     if not matching:raise ValueError('검색어와 일치하는 논문이 없습니다.')
     selected=[r['record_id'] for r in matching[:limit]];config=data.get('config',{});mode=config.get('mode','demo')
     if mode not in ['demo','live']:raise ValueError('실행 모드를 확인하세요.')
     if mode=='live':
      if not data.get('confirm_paid'):raise ValueError('실제 API 호출과 선택된 편수를 확인하세요.')
      if any(r['pmid'].startswith('DEMO-') for r in matching[:limit]):raise ValueError('실제 API 실행에는 합성 예제 대신 논문 파일을 올리세요.')
      for role in ROLES:
       roleconf=config.get('roles',{}).get(role,{})
       roleconf['max_tokens']=int(roleconf.get('max_tokens',2400))
       if not 256<=roleconf['max_tokens']<=16000:raise ValueError('응답 토큰 한도는 256~16000으로 설정하세요.')
       if roleconf.get('provider') not in PROVIDERS or not roleconf.get('key') or not roleconf.get('model'):raise ValueError(f'{ROLES[role]}의 제공자·모델·키를 설정하세요.')
     with state.lock:
      if any(j['status']=='running' for j in state.jobs.values()):raise ValueError('다른 작업이 실행 중입니다. 완료 후 시작하세요.')
      if len(state.jobs)>=10:raise ValueError('결과를 저장한 뒤 앱을 다시 시작하세요.')
      jobid=secrets.token_urlsafe(12);state.jobs[jobid]={'status':'running','events':[],'selected_count':len(selected),'matching_count':len(matching),'total_input_count':len(records),'mode':mode,'result':None}
     def work():
      def event(e):
       with state.lock:state.jobs[jobid]['events'].append(e)
      try:
       result=run_team(records,selected,config,on_event=event)
       with state.lock:state.jobs[jobid]['result']=result;state.jobs[jobid]['summary']=dict(Counter(o['status'] for o in result['outputs']));state.jobs[jobid]['status']='done'
      except Exception:
       with state.lock:state.jobs[jobid]['status']='failed';state.jobs[jobid]['error']='작업 오류입니다. 인증정보는 기록하지 않았습니다.'
      finally:
       for roleconf in config.get('roles',{}).values():roleconf['key']=''
     threading.Thread(target=work,daemon=True).start()
     self.reply(202,{'job_id':jobid,'selected_count':len(selected),'matching_count':len(matching),'max_model_calls':4*len(selected) if mode=='live' else 0});return
    self.reply(404,{'error':'경로가 없습니다.'})
   except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:
    # JSON decoding may expose input fragments through repr; use a generic message for it.
    message='요청 JSON 형식이 올바르지 않습니다.' if isinstance(e,json.JSONDecodeError) else str(e) if isinstance(e,ValueError) else '입력 항목 형식을 확인하세요.'
    self.reply(400,{'error':message})
   except ProviderError as e:self.reply(400,{'error':str(e)})
   except Exception:self.reply(500,{'error':'처리 중 오류가 발생했습니다. 키·요청 내용은 기록하지 않았습니다.'})
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.state=state;return server

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
 try:server=create_server(args.port)
 except OSError:raise SystemExit('포트를 사용할 수 없습니다. python app.py --port 8766 으로 실행하세요.')
 address=f'http://127.0.0.1:{server.server_port}'
 print('연구 에이전트 화면: '+address+'\n종료: Ctrl+C. 결과를 다운로드한 뒤 종료하세요. API 키는 파일에 저장하지 않습니다.')
 if not args.no_browser:threading.Timer(.5,lambda:webbrowser.open(address)).start()
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
