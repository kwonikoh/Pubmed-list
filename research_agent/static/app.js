'use strict';
const $=id=>document.getElementById(id),token=document.querySelector('meta[name="research-token"]').content;
const providers={anthropic:'Claude / Anthropic',deepseek:'DeepSeek',openai:'OpenAI',gemini:'Gemini / Google'};
const roleLabels={supervisor:'총괄 · 근거 대조',classifier:'장기·맥락 분류',extractor:'HIF 기능·근거 추출',critic:'독립 근거 점검'};
let datasetId='',jobId='',polling=false;
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
async function api(path,data){const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'X-Research-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'요청 오류');return result}
function busy(flag){for(const el of document.querySelectorAll('main input, main select, main textarea, main button'))el.disabled=flag}
function fail(error){$('error').textContent=error.message||String(error)}
for(const [role,label] of Object.entries(roleLabels)){
 const box=role==='supervisor'?$('supervisor'):node('div',undefined,'role');box.append(node('h3',label));
 const pl=node('label','제공자'),select=node('select');select.id=role+'-provider';for(const [id,name] of Object.entries(providers)){const o=node('option',name);o.value=id;select.append(o)}pl.append(select);box.append(pl);
 const ml=node('label','모델 ID'),model=node('input');model.id=role+'-model';model.placeholder='계정에서 사용할 수 있는 모델 ID';model.autocomplete='off';ml.append(model);box.append(ml);const tl=node('label','최대 응답 토큰'),tokens=node('input');tokens.type='number';tokens.min='256';tokens.max='16000';tokens.value='2400';tokens.id=role+'-tokens';tl.append(tokens);box.append(tl);
 select.value=role==='supervisor'?'anthropic':'deepseek';if(role!=='supervisor')$('workers').append(box)
}
for(const [provider,label] of Object.entries(providers)){
 const box=node('div',undefined,'provider');box.append(node('h3',label));const l=node('label','API 키'),key=node('input');key.type='password';key.autocomplete='off';key.spellcheck=false;key.id=provider+'-key';l.append(key);box.append(l);
 const button=node('button','사용 가능 모델 조회','secondary');button.type='button';const result=node('div','', 'models');
 button.onclick=async()=>{button.disabled=true;try{const d=await api('/api/models',{provider,key:key.value.trim()});result.textContent=d.models.join('\n')||'모델 목록이 비어 있습니다. 제공자 콘솔에서 확인하세요.'}catch(e){result.textContent=e.message}finally{button.disabled=false}};
 box.append(button,result);$('providers').append(box)
}
function updateMode(){const live=$('mode').value==='live';$('paidwrap').classList.toggle('hidden',!live);$('estimate').textContent=live?`검색 조건에 맞는 앞쪽 최대 ${$('limit').value}편을 선택합니다. 논문 1편당 담당 3회 + 총괄 1회, 최대 ${Number($('limit').value)*4}회입니다. 실제 금액은 선택한 모델·토큰 사용량에 따릅니다.`:'시연 모드: API 키·실제 모델 호출 없이 화면과 데이터 보존 흐름을 확인합니다. 업로드한 실제 논문의 기능을 분석하지는 않습니다.';if(live)$('credentials').open=true}
$('mode').onchange=updateMode;$('limit').oninput=updateMode;updateMode();
$('preset').onclick=()=>{for(const r of Object.keys(roleLabels)){$(r+'-provider').value=r==='supervisor'?'anthropic':'deepseek';$(r+'-model').value=''};$('runstatus').textContent='역할을 배치했습니다. 실제 실행 전 모델 ID를 입력하세요.'};
function showDataset(d){$('paid').checked=false;polling=false;jobId='';$('downloads').classList.add('hidden');$('events').textContent='';$('runstatus').textContent='';datasetId=d.dataset_id;$('dataset').textContent=`${d.count.toLocaleString()}편 불러옴 · 초록 ${d.abstracts.toLocaleString()}편 · 미실행 논문도 결과에 보존`;$('preview').replaceChildren();for(const r of d.preview)$('preview').append(node('li',`${r.pmid||'PMID 없음'} · ${r.title}`))}
$('demo').onclick=async()=>{busy(true);try{$('error').textContent='';showDataset(await api('/api/demo',{}));$('file').value=''}catch(e){fail(e)}finally{busy(false)}};
$('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;busy(true);try{if(file.size>40*1024*1024)throw Error('파일은 40MB 이하로 선택하세요.');$('dataset').textContent='자료를 읽는 중…';showDataset(await api('/api/import',{name:file.name,text:await file.text()}));$('error').textContent=''}catch(e){fail(e)}finally{busy(false)}};
$('run').onclick=async()=>{
 try{
  $('error').textContent='';if(!datasetId)throw Error('먼저 파일 또는 합성 예제를 불러오세요.');const roles={};
  for(const r of Object.keys(roleLabels)){const p=$(r+'-provider').value;roles[r]={provider:p,model:$(r+'-model').value.trim(),key:$(p+'-key').value.trim(),max_tokens:Number($(r+'-tokens').value)}}
  busy(true);$('downloads').classList.add('hidden');$('events').textContent='';
  const d=await api('/api/run',{dataset_id:datasetId,query:$('query').value,limit:Number($('limit').value),confirm_paid:$('paid').checked,config:{mode:$('mode').value,goal:$('goal').value,roles}});
  jobId=d.job_id;$('runstatus').textContent=`검색 일치 ${d.matching_count}편 중 ${d.selected_count}편 실행 · 나머지는 미실행으로 보존`;polling=true;poll()
 }catch(e){busy(false);fail(e)}
};
async function poll(){if(!polling)return;try{const d=await api('/api/job?id='+encodeURIComponent(jobId));$('events').textContent=d.events.map(e=>`${e.record_id} · ${roleLabels[e.stage]||e.stage}: ${e.message}`).join('\n');$('events').scrollTop=$('events').scrollHeight;if(d.status==='done'){polling=false;busy(false);$('runstatus').textContent=d.mode==='demo'?'시연 완료 — 실제 모델 분석 결과가 아닙니다.':`작업 종료 · 상태별 집계: ${JSON.stringify(d.summary)} · 검토 초안과 오류를 확인하고 결과를 저장하세요.`;$('downloads').classList.remove('hidden')}else if(d.status==='failed'){polling=false;busy(false);throw Error(d.error||'작업 실패')}else setTimeout(poll,1200)}catch(e){polling=false;busy(false);fail(e)}}
for(const button of document.querySelectorAll('[data-format]'))button.onclick=async()=>{try{button.disabled=true;const fmt=button.dataset.format;const r=await fetch(`/api/download?id=${encodeURIComponent(jobId)}&format=${fmt}`,{headers:{'X-Research-Token':token}});if(!r.ok)throw Error('결과를 저장하지 못했습니다.');const url=URL.createObjectURL(await r.blob()),a=node('a');a.href=url;a.download=`research_results.${fmt}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}catch(e){fail(e)}finally{button.disabled=false}};
