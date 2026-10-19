"""Reproducible, inclusive title/abstract/MeSH screening; not full-text adjudication.
Usage: python classify.py input.nbib [output_directory]
IF values must come from separately verified publisher/JCR data; never inferred.
"""
import sys,re,json,csv,hashlib,collections,html,zipfile,shutil
from pathlib import Path
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter
SRC=Path(sys.argv[1]); OUT=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).parent
OUT.mkdir(parents=True,exist_ok=True)
TODAY='2026-10-19'
TOPICS={
'01_장염·IBD·면역':r'colitis|inflammatory bowel|\bIBD\b|Crohn|ulcerative|Th17|T.regulatory|\bTreg|intestinal inflammation|intestinal immune|mucosal immun|enteritis|pouchitis',
'02_대장암·장종양':r'colorectal|colonic cancer|colon cancer|colon carcinoma|colon adenocarcinoma|intestinal tumo[u]?r|intestinal cancer|intestinal neoplas|colitis.associated cancer|\bCAC\b|\bAPC\b|adenoma|polyposis',
'03_장벽·상피·점액':r'intestinal barrier|epithelial barrier|mucosal barrier|gut barrier|barrier dysfunction|barrier integrity|tight junction|intestinal permeability|mucin|goblet|\bMUC2\b|claudin|occludin',
'04_허혈·재관류·저산소손상':r'isch[a]?emi|reperfusion|hypoxi[ac].{0,25}injury|hypoxi[ac].{0,25}damage|mesenteric',
'05_철·흡수·영양수송':r'\biron\b|hepcidin|ferroportin|\bDMT1\b|\bDcytb\b|\bSLC11A2\b|\bSLC40A1\b|\bTFRC\b|nutrient absorption|intestinal absorption|glucose transport|copper absorption|iron deficiency',
'06_미생물·감염·미생물대사':r'microbiot|microbiom|microbial|dysbiosis|butyrate|short.chain fatty|Clostridi|Salmonella|Yersinia|Citrobacter|Faecalibacterium|enteric infection|intestinal infection|bacterial infection|probiotic',
'07_재생·줄기세포·오가노이드':r'regeneration|regenerative|intestinal repair|mucosal healing|wound healing|intestinal stem|crypt stem|\bLGR5\b|organoid|enteroid|intestinal restitution|crypt regeneration',
'08_대사·비만·장간축':r'obesity|obese|insulin resistance|diabetes|metabolic syndrome|steatohepatitis|\bMASLD\b|\bNAFLD\b|\bNASH\b|gut.liver|intestinal gluconeogenesis|lipid absorption|high.fat diet|western diet',
'09_장섬유화·기질':r'fibrosis|fibrotic|intestinal stricture|epithelial.mesenchymal|\bEMT\b|extracellular matrix|myofibroblast',
'10_혈관·내피·혈관신생':r'angiogenesis|angiogenic|microvascul|endothelial|vascular permeability|\bVEGF[A-Z0-9]*\b|vascular endothelial',
'11_신생아·발달·NEC':r'necrotizing enterocolitis|necrotising enterocolitis|\bNEC\b|neonatal|premature infant|preterm infant|intestinal development|intestinal maturation',
'12_방사선·패혈증·전신손상':r'radiation|irradiation|radiotherapy|sepsis|septic|endotoxic|endotoxemia|pancreatitis|graft.versus.host|\bGVHD\b|intestinal transplantation|intestinal transplant',
'13_운동·장신경·내분비':r'motility|peristal|enteric nerv|enteric neuron|enteroendocrine|\bGLP.1\b|glucagon.like peptide|serotonin|intestinal smooth muscle|gut.brain',
'14_细胞代谢·死亡·氧感知':r'glycolysis|glycolytic|ferroptosis|autophagy|mitochondri|pyroptosis|necroptosis|prolyl hydroxyl|\bPHD[123]?\b|\bEGLN[123]?\b|\bVHL\b|oxygen.sensing|hypoxia.inducible|\bHIF[ -]?[12]',
'15_약물·전달·치료기전':r'\bDMOG\b|dimethyloxal|dimethyl oxal|roxadustat|vadadustat|daprodustat|molidustat|belzutifan|\bPT2385\b|\bPT2399\b|\bAKB.4924\b|GB004|hydroxylase inhibitor|drug delivery|nanoparticle|nanocarrier|hydrogel',
}
# Use a Korean title in the workbook; stable key retained in this script.
TOPICS['14_세포대사·세포사멸·산소감지']=TOPICS.pop('14_细胞代谢·死亡·氧感知')
TOPICS=dict(sorted(TOPICS.items()))
RX={k:re.compile(v,re.I) for k,v in TOPICS.items()}
ANAT={
'십이지장':r'duoden', '공장':r'jejun', '회장':r'\bileum\b|\bileal\b|ileitis',
'소장(부위미상)':r'small.intestin|small.bowel', '대장·결장':r'colon|colitis|colorectal|large.intestin|large.bowel',
'직장':r'rectal|rectum', '장(부위미상)':r'intestin|\bgut\b|\bbowel\b|enterocol|enterocyte|enteroid|enteric',
'장유래세포주':r'Caco.?2|HT.?29|HCT.?116|DLD.?1|SW.?480|SW.?620|LoVo|T84|MC38|CT26'}
CELL={'cell','cancer cell','cell metabolism','cell host & microbe','cell stem cell','cell reports','cell reports medicine','cell reports methods','cell systems','immunity','molecular cell','current biology','developmental cell','iscience','med','trends in immunology','trends in cancer','trends in molecular medicine','trends in cell biology','trends in endocrinology and metabolism: tem'}
NATURE={'oncogene','oncogenesis','cell research','cell discovery','cell death & disease','cell death and differentiation','cell death discovery','cellular & molecular immunology','experimental & molecular medicine','signal transduction and targeted therapy','scientific reports'}
KO=re.compile(r'\bknock[ -]?out\b|\bKO\b|conditional(?:ly)? (?:\w+[ -]){0,3}delet\w*|(?:[A-Za-z0-9αβ+()/-]+[ -]){0,2}specific (?:\w+ ){0,2}deletion|genetic(?:ally)? (?:\w+ ){0,2}(?:deletion|deleted|ablat\w*)|(?:Hif[ -]?[12][aα]?|Epas1|HIF[ -]?[12][aα]?)[ -](?:delet\w*|null)|(?:mice|mouse|animals) lacking|(?:deletion|ablation) of (?:the )?(?:[A-Za-z0-9αβ-]+ )?(?:gene|HIF|Hif|EPAS)|\b[A-Za-z0-9]+\s*\(?-/-\)?',re.I)
KOCAND=re.compile(r'\bdeficien\w*\b|\bnull mice\b|\bCre(?:ERT2)?\b|\bflox\w*\b',re.I)
KD=re.compile(r'knock[ -]?down|\bsiRNA\b|\bshRNA\b|gene silencing',re.I)
DMOG=re.compile(r'\bDMOG\b|dimethyl\s*oxal\w*(?:\s*glycine)?|dimethyloxal\w*',re.I)

def parse():
 records=[]
 for i,raw in enumerate(re.split(r'(?m)(?=^PMID- )',SRC.read_text(encoding='utf-8-sig')),1):
  if not raw.startswith('PMID- '):continue
  d={};key=None
  for l in raw.splitlines():
   m=re.match(r'^([A-Z0-9]{2,4})\s*-\s?(.*)',l)
   if m:key=m[1];d.setdefault(key,[]).append(m[2])
   elif l.startswith('      ') and key:d[key][-1]+=' '+l.strip()
  records.append(d)
 return records

def sentence(text,rx):
 ss=re.split(r'(?<=[.!?])\s+(?=[A-Z(])',text)
 hits=[s.strip() for s in ss if rx.search(s)]
 return '\n'.join(hits[:5])

def family(j):
 j=j.lower().strip()
 if j in CELL:return 'Cell Press','본지' if j=='cell' else '자매지',0
 if j=='nature' or j.startswith('nature ') or j.startswith('npj ') or j in NATURE:return 'Nature Portfolio','본지' if j=='nature' else '자매지',0
 if j in {'science (new york, n.y.)','science','science advances','science immunology','science translational medicine','science signaling','science robotics'}:return 'Science/AAAS','본지' if j in {'science','science (new york, n.y.)'} else '자매지',0
 if j=='british journal of cancer' or j.startswith('laboratory investigation'):return '연관/과거 Nature 플랫폼—범위 확인','확인 필요',1
 return '기타','',2

def fget(d,k):return ' | '.join(d.get(k,[]))

def classify(d,i):
 title=fget(d,'TI');ab=fget(d,'AB');mesh=fget(d,'MH');text=title+' '+ab;indexed=text+' '+mesh
 journal=fget(d,'JT') or fget(d,'TA'); fam,sub,rank=family(journal)
 hits={k:list(dict.fromkeys(m.group(0) for m in rx.finditer(indexed)))[:15] for k,rx in RX.items() if rx.search(indexed)}
 # Broad mechanism tag is secondary whenever a more specific organ/disease topic exists.
 specifics=[k for k in hits if not k.startswith(('14_','15_'))]
 candidates=specifics or list(hits)
 primary=max(candidates,key=lambda k:(len(RX[k].findall(title))*5+min(len(RX[k].findall(ab)),8),-list(RX).index(k))) if candidates else '16_기타·관련성검토'
 topics=sorted(hits) if hits else [primary]
 anatomy=[k for k,v in ANAT.items() if re.search(v,indexed,re.I)]
 direct_title=any(re.search(v,title,re.I) for v in ANAT.values())
 rel='제목에 장/장유래세포 명시' if direct_title else '초록/MeSH에 장/장유래세포 언급' if anatomy else '장 관련성 추가 확인'
 h1=bool(re.search(r'HIF[ -]?1|HIF1A|hypoxia.inducible factor[ -]?1',text,re.I))
 h2=bool(re.search(r'HIF[ -]?2|HIF2A|EPAS[ -]?1|hypoxia.inducible factor[ -]?2',text,re.I))
 iso='HIF-1 + HIF-2' if h1 and h2 else 'HIF-1' if h1 else 'HIF-2' if h2 else 'HIF/PHD 일반·아형 확인'
 pt=d.get('PT',[]); review=any('Review' in x or x=='Meta-Analysis' for x in pt)
 typeflags=[]
 if review:typeflags.append('리뷰/메타분석')
 if any('Clinical Trial' in x or x=='Randomized Controlled Trial' for x in pt):typeflags.append('임상시험(PubMed PT)')
 if 'Observational Study'in pt:typeflags.append('관찰연구(PubMed PT)')
 if 'Case Reports'in pt:typeflags.append('증례(PubMed PT)')
 if re.search(r'\bHumans\b',mesh):typeflags.append('인체 연구(MeSH)')
 if re.search(r'\bAnimals\b',mesh):typeflags.append('동물 연구(MeSH)')
 if re.search(r'\bmice\b|\bmouse\b|\brats\b|\brat model|murine|porcine|piglets|zebrafish',text,re.I) and '동물 연구(MeSH)' not in typeflags:typeflags.append('동물모델 언급')
 if re.search(r'in vitro|cell line|cultured|Caco.?2|HT.?29|HCT.?116|organoid|enteroid',text,re.I):typeflags.append('세포/오가노이드 언급')
 if re.search(r'patient|clinical sample|human biopsy|human biopsies|human tissue',text,re.I) and '인체 연구(MeSH)' not in typeflags:typeflags.append('환자/인체시료 언급(임상시험 아님)')
 types='; '.join(typeflags) or '연구 유형 추가 확인'
 if 'Book Chapter' in pt:types='도서 장(저널 원저 아님); '+types
 ko=bool(KO.search(text) or re.search(r'\b(?:Mice|Animals), Knockout\b',mesh,re.I));kc=bool(KOCAND.search(re.sub(r'(?:iron|oxygen|vitamin(?: [A-Z0-9]+)?|zinc|copper|selenium|nutrient|nutritional|folate|cobalamin|respiration|energy)[ -]deficien\w*','',text,flags=re.I))); dm=bool(DMOG.search(text));kd=bool(KD.search(text))
 kost='KO/유전자결손 명시(초록/MeSH)—직접 사용 확인 필요' if ko else '결손/Cre 언급—KO 후보' if kc else '확인 필요(초록에 명시 없음)'
 if ko and review:kost='리뷰 내 KO 언급—자체 실험 아님'
 dmst='DMOG 명시—직접 사용 확인 필요' if dm else '확인 필요(초록에 명시 없음)'
 if dm and review:dmst='리뷰 내 DMOG 언급—자체 실험 아님'
 # Display NBIB DP as supplied; never use LR as publication date.
 dp=fget(d,'DP'); ym=re.search(r'\b(?:19|20)\d{2}\b',dp);year=int(ym[0]) if ym else 0
 year_source='DP(저널 권호 출판연도)'
 if 'Book Chapter' in pt and d.get('CTDT'):
  year=int(d['CTDT'][0][:4]);year_source='CTDT(도서 장 생성일; DP는 시리즈 시작연도)'
 elif year>2026 and d.get('DEP') and int(d['DEP'][0][:4])<=2026:
  year=int(d['DEP'][0][:4]);year_source='DEP(선출판; 권호연도는 미래)'
 flags=[]
 if not ab:flags.append('초록 없음')
 if 'Book Chapter' in pt:flags.append('도서 장—저널 원저 아님; DP 시리즈 연도 주의')
 if int(ym[0])<1995 if ym else False:flags.append('DP 1995년 이전—원본 보존·정렬연도 근거 참조')
 if ym and int(ym[0])>2026:flags.append('미래 권호연도—DEP 선출판 연도 사용')
 if any('Retract' in p for p in pt):flags.append('철회 논문/철회 공지(PubMed PT)')
 if any('Erratum' in p or 'Correction' in p for p in pt):flags.append('정정 공지')
 if 'Preprint'in pt or 'biorxiv' in journal.lower():flags.append('프리프린트—동료심사 완료 아님')
 if rel=='장 관련성 추가 확인':flags.append('장 관련성 확인 필요')
 doi=next((v.replace(' [doi]','') for v in d.get('LID',[])+d.get('AID',[]) if v.endswith('[doi]')),'')
 pmid=fget(d,'PMID')
 row={'원본순번':i,'주제(대표)':primary,'주제(전체)':'; '.join(topics),'연도':year,'출판일_DP':dp,'정렬연도근거':year_source,'도서장생성_CTDT':fget(d,'CTDT'),'CNS계열':fam,'본지/자매지':sub,'IF':None,'IF기준연도':None,'IF검증':'미검증—NBIB 미수록·공식 지표 페이지 접근 차단','KO분류':kost,'DMOG분류':dmst,'KO우선점수':0 if ko and not review else 1 if kc and not review else 2,'DMOG우선점수':0 if dm and not review else 1,'PMID':pmid,'제목':title,'저널':journal,'저널약어':fget(d,'TA'),'PubMed링크':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/','DOI':doi,'DOI링크':f'https://doi.org/{doi}' if doi else '', '장부위(전체)':'; '.join(anatomy) or '미확인','장관련성':rel,'HIF아형':iso,'HIF관련성':('제목/초록에 HIF-1/2 명시' if h1 or h2 else 'MeSH에 HIF 명시' if re.search(r'hypoxia.inducible factor|HIF',mesh,re.I) else 'HIF 직접 관련성 추가 확인'),'연구유형':types,'PubMed출판유형':'; '.join(pt),'KO근거문장':sentence(text,KO) or ('MeSH: '+ '; '.join(m for m in d.get('MH',[]) if re.search(r'(?:Mice|Animals), Knockout',m,re.I)) if ko else ''),'KO후보근거문장':sentence(text,KOCAND) if not ko else '', 'Knockdown별도':sentence(text,KD),'DMOG근거문장':sentence(text,DMOG),'주제분류근거':'; '.join(k+': '+', '.join(v) for k,v in hits.items()),'검토표시':'; '.join(flags),'초록':ab,'MeSH':mesh,'온라인출판_DEP':fget(d,'DEP'),'저자':fget(d,'FAU'),'언어':fget(d,'LA'),'CNS정렬값':rank,'IF출처':'','원본DP보존':dp}
 return row,topics

rs=parse(); classified=[classify(d,i) for i,d in enumerate(rs,1)]; rows=[a for a,b in classified]
FIELDS=list(rows[0])
def sortyear(r):return (-r['연도'],r['CNS정렬값'],-(r['IF'] or -1),0 if r['KO우선점수']==0 else 1,r['DMOG우선점수'],r['KO우선점수'],int(r['PMID']))
def priority(r):return (r['CNS정렬값'],-(r['IF'] or -1),0 if r['KO우선점수']==0 else 1,r['DMOG우선점수'],r['KO우선점수'],-r['연도'],int(r['PMID']))
def safe(v):
 if isinstance(v,str) and v.startswith(('=','+','-','@')):return "'"+v
 return v

def csvout(name,data):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows({k:safe(r[k]) for k in FIELDS} for r in data)
master=sorted(rows,key=lambda r:(r['주제(대표)'],*sortyear(r)))
csvout('HIF_intestine_master.csv',master)
(OUT/'parsed_records.json').write_text(json.dumps(rs,ensure_ascii=False),encoding='utf-8')
counts=collections.Counter(k for _,topics in classified for k in topics)
prim=collections.Counter(r['주제(대표)'] for r in rows)
familycounts=collections.Counter(r['CNS계열'] for r in rows)
stats={'input_records':len(rs),'unique_pmids':len({r['PMID'] for r in rows}),'all_preserved':len(rows)==len(rs),'abstracts':sum(bool(r['초록']) for r in rows),'CNS_counts':dict(familycounts),'KO_abstract_or_MeSH_mentions':sum(bool(r['KO근거문장']) for r in rows),'KO_explicit_nonreview':sum(r['KO우선점수']==0 for r in rows),'KO_candidate_nonreview':sum(r['KO우선점수']==1 for r in rows),'DMOG_mentions':sum(bool(r['DMOG근거문장']) for r in rows),'DMOG_nonreview':sum(r['DMOG우선점수']==0 for r in rows),'topics_multilabel':dict(sorted(counts.items())),'primary_topics':dict(sorted(prim.items())),'year_counts':dict(sorted(collections.Counter(r['연도'] for r in rows).items())),'IF_values_verified':sum(r['IF'] is not None for r in rows),'NBIB_SHA256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'generated':TODAY,'method':'rule-based title/abstract/MeSH screening; no full-text or model adjudication','PubMed_API_check':'esummary PMID 42893454 HTTP 200 on 2026-10-19','IF_access':'nature.com and gut.bmj.com and gastrojournal.org official metric requests returned proxy tunnel 403; no estimated IF values used'}
(OUT/'validation.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
notes=[
['자료','첨부 NBIB 전체 2,525편; 입력과 PMID 전수 대조. PubMed API 연결 확인. 새 전수 검색이나 누락 검증은 시행하지 않음.'],
['범위','DP가 1993인 GeneReviews 도서 장(CTDT 2026)과 2027 권호/2026 선출판 항목도 삭제하지 않고 검토 표시. 일반 논문은 DP 기준; 미래 권호 항목은 DEP 선출판 연도, 도서 장은 CTDT 생성 연도로 정렬. DP 원본·정렬연도 근거를 함께 보존. LR 갱신일은 출판일로 사용하지 않음.'],
['주제','제목·초록·MeSH 키워드 규칙 기반 복수 분류. 의미 판독을 마친 확정 분류가 아닌 스크리닝. 주제 시트 간 동일 PMID 중복은 의도됨.'],
['연도별 정렬','각 주제 내 연도 내림차순 → CNS → 확인된 IF 내림차순 → KO 명시 → DMOG 명시 → KO 후보. IF 미확인으로 IF 정렬은 현재 작동하지 않음.'],
['우선검토 시트','전체 연도 통합: CNS → IF → KO 명시 → DMOG → KO 후보 → 최신연도. 연도별 시트와 우선순위 목적이 다름.'],
['KO','KO/knockout/조건부 유전자결손 명시 및 MeSH Mice, Knockout를 우선 표시. HIF 유전자 자체의 KO와 상위·하위 유전자 KO를 모두 포함하며 원문 근거문장 제공. 일반 deficiency는 별도 후보, knockdown/siRNA/shRNA는 별도 열. 직접 실험 사용·표적·세포 특이성은 전문 확인 필요.'],
['DMOG','DMOG 및 dimethyloxalylglycine 표기를 탐지. 다른 PHD 억제제를 DMOG로 간주하지 않음. 문헌 인용·논의·자체 처치 구별은 전문 확인 필요. 리뷰의 언급은 별도 표시하고 실험 우선순위에서 제외.'],
['CNS','Cell Press, Nature Portfolio, Science/AAAS 지정 명칭 목록. Cell이라는 단어가 있다는 이유로 Cell Press에 포함하지 않음. British Journal of Cancer 및 Laboratory Investigation은 연관/과거 플랫폼으로 따로 표시; 연도별 출판사 변동 전수 검증 미완료.'],
['IF','NBIB에 JIF는 없음. 공식 출판사 지표 사이트 접근이 403 차단되어 IF/기준연도는 공란. 2024/2025 값이나 IF≥10을 추정하지 않음. journal_IF_template.csv에 검증 값·기준연도·출처 입력 가능.'],
['연구 유형','PubMed PT/MeSH 정보와 제목·초록의 모델 언급을 구분해 기재. 환자 또는 인체시료 연구를 임상시험으로 간주하지 않음.'],
['보존','전체 원본은 source.nbib, 파싱된 전체 필드는 parsed_records.json. 리뷰·철회·정정·프리프린트·장 관련성 불명 문헌도 삭제하지 않음.'],
['초록 미언급','KO/DMOG 근거가 없다는 것은 미사용을 뜻하지 않음. 확인 필요로 기록.'],
['HIF아형','HIF-1/HIF1A, HIF-2/EPAS1 제목·초록 탐지; 두 아형이 언급되어도 둘 다 직접 실험했다는 뜻은 아님.'],
['계산','분류 키워드·재현 코드 classify.py. 재실행에는 Python+openpyxl 필요. 연구 결론 또는 약물의 인과적 효능을 자동 확정하지 않음.']]
wb=Workbook();ws=wb.active;ws.title='사용안내'
ws.append(['항목','설명']);[ws.append(x) for x in notes]

COMPACT=[k for k in FIELDS if k not in ['초록','MeSH','저자','언어','원본DP보존','도서장생성_CTDT','저널약어','IF검증','원본순번','주제분류근거']]
def sheet(name,data,fields=None):
 fields=fields if fields is not None else (FIELDS if name=='전체_주제연도' else COMPACT)
 ws=wb.create_sheet(name[:31]);ws.append(fields)
 for r in data:
  ws.append([safe(r.get(k,'')) for k in fields])
  for j,k in enumerate(fields,1):
   if k in ('PubMed링크','DOI링크') and r.get(k):ws.cell(ws.max_row,j).hyperlink=r[k];ws.cell(ws.max_row,j).style='Hyperlink'
 return ws
sheet('전체_주제연도',master)
sheet('우선검토_CNS_KO_DMOG',sorted(rows,key=priority))
sheet('CNS_확정계열',[r for r in sorted(rows,key=priority) if r['CNS정렬값']==0])
sheet('KO_명시후보',[r for r in sorted(rows,key=priority) if r['KO우선점수']<2])
sheet('DMOG_언급전체',[r for r in sorted(rows,key=priority) if r['DMOG근거문장']])
sheet('검토필요_철회날짜등',[r for r in sorted(rows,key=sortyear) if r['검토표시']])
for topic in sorted(counts):
 data=[r for r,topics in classified if topic in topics]
 sheet(topic,sorted(data,key=sortyear))
summary=wb.create_sheet('주제별집계');summary.append(['주제','복수분류 논문수','대표주제 논문수'])
for k,n in sorted(counts.items()):summary.append([k,n,prim[k]])
summary=wb.create_sheet('연도별집계');summary.append(['출판연도','전체','CNS확정','KO명시_비리뷰','DMOG명시_비리뷰'])
for year in sorted(set(r['연도'] for r in rows),reverse=True):
 subset=[r for r in rows if r['연도']==year];summary.append([year,len(subset),sum(r['CNS정렬값']==0 for r in subset),sum(r['KO우선점수']==0 for r in subset),sum(r['DMOG우선점수']==0 for r in subset)])
# Journal-level IF fill-in template, zero fabricated values.
journals=collections.defaultdict(list)
for r in rows:journals[r['저널']].append(r)
jrows=[{'저널':j,'편수':len(v),'CNS계열':v[0]['CNS계열'],'IF':'','IF기준연도':'','IF출처':'','검증상태':'미확인'} for j,v in sorted(journals.items(),key=lambda kv:(kv[1][0]['CNS정렬값'],-len(kv[1]),kv[0]))]
with (OUT/'journal_IF_template.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(jrows[0]));w.writeheader();w.writerows(jrows)
sheet('저널_IF검증대기',jrows,list(jrows[0]))
for ws in wb:
 ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
 for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='164B60')
 for col in ws.columns:
  key=col[0].value;ws.column_dimensions[col[0].column_letter].width=60 if key in ['제목','설명'] else 55 if key in ['초록','KO근거문장','DMOG근거문장','KO후보근거문장','Knockdown별도','주제분류근거'] else 28 if key in ['주제(대표)','저널','CNS계열','연구유형','KO분류','DMOG분류','검토표시'] else 18
 ws.row_dimensions[1].height=30
 for row in ws.iter_rows(min_row=2):
  for c in row:c.alignment=Alignment(vertical='top',wrap_text=True)
  ws.row_dimensions[row[0].row].height=42
wb.save(OUT/'HIF_intestine_1995_classified.xlsx')
# HTML mirrors Excel topic/year grouping and works without Excel or any server.
E=lambda x:html.escape(str(x or ''))
parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>소장·대장 HIF 문헌 스크리닝</title><style>body{font:15px system-ui;max-width:1200px;margin:32px auto;padding:0 18px;color:#173344}nav{display:flex;flex-wrap:wrap;gap:10px}article{padding:15px;border-bottom:1px solid #ccd8dd}h2{background:#164b60;color:white;padding:12px}h3{border-bottom:2px solid #abc}small{display:block;color:#526570}summary{cursor:pointer}input{position:sticky;top:0;width:95%;padding:12px;background:#fff}mark{background:#dceffa}.note{background:#fff2d6;padding:15px}</style><h1>소장·대장 HIF-1·HIF-2 문헌 스크리닝</h1>',f'<p>{len(rows):,}편 · PMID 전수 보존 · {TODAY} 작성</p><p class="note">제목·초록·MeSH 키워드 기반 후보 분류입니다. IF는 검증되지 않아 비워 두었습니다. KO·DMOG 언급은 직접 사용 확정이 아닙니다. 리뷰·철회·프리프린트는 표시 후 보존했습니다.</p><input id="q" placeholder="제목·저널·PMID·KO·DMOG 검색"><nav>']
for k,n in sorted(counts.items()):parts.append(f'<a href="#{E(k)}">{E(k)} ({n})</a>')
parts.append('</nav>')
for k in sorted(counts):
 parts.append(f'<section id="{E(k)}"><h2>{E(k)} ({counts[k]}편)</h2>');year=None
 for r in sorted([r for r,topics in classified if k in topics],key=sortyear):
  if year!=r['연도']:year=r['연도'];parts.append(f'<h3>{year}년</h3>')
  badges=[]
  if r['CNS정렬값']==0:badges.append(r['CNS계열'])
  if r['KO근거문장']:badges.append('KO 언급')
  if r['DMOG근거문장']:badges.append('DMOG 언급')
  parts.append(f'<article><b>{E(r["제목"])}</b> <mark>{E(" · ".join(badges))}</mark><small>{E(r["저널"])} · {E(r["HIF아형"])} · {E(r["연구유형"])}</small><a href="{E(r["PubMed링크"])}">PMID {E(r["PMID"])}</a> · {E(r["장부위(전체)"])}<small>{E(r["검토표시"])}</small><details><summary>초록·실험 근거</summary><p>{E(r["초록"])}</p><p><b>KO:</b> {E(r["KO분류"])}<br>{E(r["KO근거문장"])}</p><p><b>DMOG:</b> {E(r["DMOG분류"])}<br>{E(r["DMOG근거문장"])}</p></details></article>')
 parts.append('</section>')
parts.append('<script>document.getElementById("q").addEventListener("input",function(){let q=this.value.toLowerCase();document.querySelectorAll("article").forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q))})</script></html>')
(OUT/'HIF_intestine_browser.html').write_text(''.join(parts),encoding='utf-8')
shutil.copyfile(SRC,OUT/'source.nbib')
readme='# 소장·대장 HIF-1·HIF-2 문헌: 1995년부터 첨부 자료 분류\n\n'
readme+='첨부 자료 2,525편을 보존했습니다. 신규 PubMed 전수검색 결과나 최종 전문 검토 목록이 아닙니다.\n\n'
readme+='- [엑셀](HIF_intestine_1995_classified.xlsx)\n- [CSV](HIF_intestine_master.csv)\n- [브라우저용 HTML: 내려받아 열기](HIF_intestine_browser.html)\n- [전체 패키지](HIF_intestine_1995_package.zip)\n\n'
for k,v in notes:readme+=f'**{k}**: {v}\n\n'
readme+='## 분류 집계\n\n|주제|복수분류 편수|대표주제 편수|\n|---|---:|---:|\n'
for k,n in sorted(counts.items()):readme+=f'|{k}|{n}|{prim[k]}|\n'
readme+='\n## 재현\n\n`python classify.py source.nbib 출력폴더` (Python 3 + openpyxl). IF 검증값은 자동으로 추정하거나 적용하지 않습니다.\n'
(OUT/'README.md').write_text(readme,encoding='utf-8')
# Check output independently by reopening workbook and comparing every master PMID.
check=load_workbook(OUT/'HIF_intestine_1995_classified.xlsx',read_only=True,data_only=False)
ws=check['전체_주제연도'];it=ws.values;head=next(it);pcol=head.index('PMID');saved=[str(row[pcol]) for row in it]
assert collections.Counter(saved)==collections.Counter(r['PMID'] for r in rows)
assert sum(prim.values())==len(rows)
assert all(not r['DMOG근거문장'] or DMOG.search(r['DMOG근거문장']) for r in rows)
assert all(not r['KO근거문장'] or KO.search(r['KO근거문장']) or r['KO근거문장'].startswith('MeSH:') for r in rows)
assert all(r['IF'] is None for r in rows)
check.close()
stats['xlsx_reopen_PMid_multiset_validation']='passed';stats['xlsx_sheets']=len(wb.sheetnames)
(OUT/'validation.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
archive=OUT/'HIF_intestine_1995_package.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(OUT.iterdir()):
  if p.is_file() and p!=archive and p.name not in ['.DS_Store']:z.write(p,p.name)
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps(stats,ensure_ascii=False,indent=2))
print('OUTPUTS',[(p.name,p.stat().st_size) for p in OUT.iterdir() if p.is_file()])
