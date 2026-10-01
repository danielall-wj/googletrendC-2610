const $ = s => document.querySelector(s);
const names = { KR: '대한민국', US: '미국', JP: '일본' };
const periods = { '7d': ['지난 1주', 'now 7-d'], '1m': ['지난 1개월', 'today 1-m'], '3m': ['지난 3개월', 'today 3-m'], '12m': ['지난 1년', 'today 1-y'] };
const params = new URLSearchParams(location.search);
const state = { view: params.get('view') === 'explore' ? 'explore' : 'trending', geo: names[params.get('geo')] ? params.get('geo') : 'KR', hours: [4,12,24,48,168].includes(Number(params.get('hours'))) ? Number(params.get('hours')) : 24, period: periods[params.get('period')] ? params.get('period') : '1m', type: params.get('type') === 'rising' ? 'rising' : 'top', category: params.get('cat') || 'all', query: params.get('q') || '' };
let index = null, data = null, visible = [], requestId = 0, historyId = 0, snapshots = [], historical = false, nextCheck = Date.now() + 300000;
let selectedKeyword = null;
const fmt = new Intl.NumberFormat('ko-KR');
const dateFmt = new Intl.DateTimeFormat('ko-KR', { timeZone:'Asia/Seoul', month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false });
const date = value => value ? dateFmt.format(new Date(value)) : '—';
const fullDate = value => value ? new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '—';
const volume = n => n >= 10000 ? `${fmt.format(n/10000)}만+` : `${fmt.format(n)}+`;
function el(tag,text,cls) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node; }
function link(label,href) { const a=el('a',label);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a; }
function safeUrl(value) { try { const u=new URL(value);return ['https:','http:'].includes(u.protocol) ? u.href : null; } catch{return null;} }
function sourceUrl(){ return state.view==='explore' ? `https://trends.google.co.kr/explore?geo=${state.geo}&date=${encodeURIComponent(periods[state.period][1])}` : `https://trends.google.co.kr/trending?geo=${state.geo}&hours=${state.hours===12?24:state.hours}`; }
function updateUrl(){ const p=new URLSearchParams({view:state.view,geo:state.geo});if(state.view==='explore'){p.set('period',state.period);p.set('type',state.type);}else{p.set('hours',state.hours);if(state.category!=='all')p.set('cat',state.category);}if(state.query)p.set('q',state.query);history.replaceState(null,'',`${location.pathname}?${p}${location.hash}`); }
async function json(path){ const response=await fetch(`./data/${path}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});if(!response.ok)throw new Error(response.status===404?'이 국가·기간의 수집 데이터가 아직 없습니다.':`데이터 요청 오류 (${response.status})`);return response.json(); }
function configure(){
  const explore=state.view==='explore';
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));
  $('#heading').textContent=explore?'사람들이 많이 검색한 검색어':'지금, 무엇을 찾고 있나요?';
  $('#subtitle').textContent=explore?'한 주부터 일 년까지, 관심의 흐름을 살펴보세요.':'검색으로 읽는 세상의 관심사.';
  $('#region-label').textContent=`${names[state.geo]} · ${state.geo}`;$('#geo').value=state.geo;$('#search').value=state.query;
  $('#source').href=sourceUrl();$('#periods').replaceChildren();
  const values=explore?Object.entries(periods).map(([key,v])=>[key,v[0]]):[4,12,24,48,168].map(h=>[h,h===168?'7일':`${h}시간`]);
  for(const [value,label] of values){const b=el('button',label);b.setAttribute('aria-pressed',String(explore?state.period===value:state.hours===value));b.addEventListener('click',()=>{if(explore)state.period=value;else state.hours=value;resetHistory();updateUrl();configure();load();});$('#periods').append(b);}
  $('#explore-controls').hidden=!explore;$('#categories').hidden=explore;$('#sort').hidden=explore;$('#active-control').hidden=explore;$('#history-toggle').hidden=explore;
  $('#stat-label-1').textContent=explore?'상위 검색어':'조회된 검색어';$('#stat-label-2').textContent=explore?'급상승 검색어':'현재 상승 중';$('#stat-label-3').textContent=explore?'상위 검색어 1위':'가장 많이 검색한 키워드';
  document.querySelectorAll('[data-type]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.type===state.type)));
  $('#metric-note').textContent=state.type==='top'?'관심도는 최고 항목을 100으로 둔 상대 점수입니다. 순위 변동은 직전 같은 길이의 달력 일자 구간과 비교한 자체 계산값으로, Google 화면의 변화율과 다릅니다.':'직전 비교 기간 대비 검색 증가율입니다. ‘급등’은 5,000% 초과 증가를 뜻하며 실제 검색 횟수가 아닙니다.';
}
function renderCategories(){
  const container=$('#categories');container.replaceChildren();if(!data||state.view==='explore')return;
  const present=new Set(data.trends.flatMap(t=>t.categories));
  const choices=[['all','전체'],...Object.entries(index?.categories||{}).filter(([id])=>present.has(Number(id)))];
  for(const id of present)if(!index?.categories?.[id])choices.push([String(id),`기타 (${id})`]);
  for(const [id,label] of choices){const b=el('button',label);b.setAttribute('aria-pressed',String(state.category===id));b.addEventListener('click',()=>{state.category=id;updateUrl();renderCategories();render();});container.append(b);}
}
function trendList(){const list=data?.trends||[];return state.hours===12?list.filter(t=>{const age=Date.parse(data.fetched_at)-Date.parse(t.started_at);return age>=0&&age<=43200000;}):list;}
function render(){
  const explore=state.view==='explore';const list=explore?(data?.[state.type]||[]):trendList();
  $('#total').textContent=data?fmt.format(explore?data.top.length:list.length):'—';$('#active').textContent=data?fmt.format(explore?data.rising.length:list.filter(t=>!t.ended_at).length):'—';
  $('#top').textContent=explore?(data?.top?.[0]?.query||'—'):([...list].sort((a,b)=>b.volume-a.volume)[0]?.keyword||'—');
  const query=state.query.toLocaleLowerCase();
  visible=list.filter(t=>explore?t.query.toLocaleLowerCase().includes(query):(!$('#only-active').checked||!t.ended_at)&&(state.category==='all'||t.categories.includes(Number(state.category)))&&[t.keyword,...t.related].some(k=>k.toLocaleLowerCase().includes(query)));
  if(!explore){const sort=$('#sort').value;if(sort==='volume')visible.sort((a,b)=>b.volume-a.volume);if(sort==='growth')visible.sort((a,b)=>b.increase_pct-a.increase_pct);if(sort==='recent')visible.sort((a,b)=>Date.parse(b.started_at)-Date.parse(a.started_at));}
  const headers=explore?['순위','검색어',state.type==='top'?'검색 관심도':'증가율',state.type==='top'?'순위 변동':'구분']:['순위','검색어 / 관련 키워드','검색량','증가율','시작 시각 (KST)','상태'];
  const header=el('tr');for(const text of headers){const th=el('th',text);th.scope='col';header.append(th);}$('#columns').replaceChildren(header);
  const fragment=document.createDocumentFragment();const previous=new Set(data?.prev_keywords||[]);
  visible.forEach((t,i)=>{
    const row=el('tr');row.append(el('td',String(explore?t.rank:i+1).padStart(2,'0')));
    const cell=el('td',undefined,'keyword');const b=el('button',explore?t.query:t.keyword);b.addEventListener('click',()=>openDetail(t));cell.append(b);
    if(!explore&&data.previous_fetched_at&&!previous.has(t.keyword))cell.append(el('span','NEW','badge new'));
    if(!explore){const related=t.related.filter(k=>k!==t.keyword).slice(0,3);if(related.length)cell.append(el('span',related.join(' · '),'related'));}
    row.append(cell);
    if(explore){
      const score=el('td',undefined,'score-cell');const wrap=el('div',undefined,'score');const meter=el('meter');meter.min=0;meter.max=state.type==='top'?100:Math.max(1,...list.filter(x=>!x.is_breakout).map(x=>x.value));meter.value=t.is_breakout?meter.max:t.value;meter.setAttribute('aria-label',state.type==='top'?'상대 관심도':'상승률');wrap.append(meter,el('span',state.type==='top'?fmt.format(t.value):t.is_breakout?'급등':`+${fmt.format(t.value)}%`));score.append(wrap);
      const change=state.type==='top'?(data.comparison_status!=='ok'?'비교 없음':t.is_new?'NEW':t.rank_change===0?'—':`${t.rank_change>0?'▲':'▼'} ${Math.abs(t.rank_change)}`):(t.is_breakout?'폭발적 증가':'상승');
      row.append(score,el('td',change,t.rank_change<0?'negative':'growth'));
    }else{const status=el('td');status.append(el('span',t.ended_at?'종료':'상승 중',t.ended_at?'badge ended':'badge'));row.append(el('td',volume(t.volume)),el('td',`↗ ${fmt.format(t.increase_pct)}%`,'growth'),el('td',date(t.started_at),'date'),status);}
    fragment.append(row);
  });
  $('#rows').replaceChildren(fragment);$('#empty').hidden=!data||visible.length>0;$('#export-csv').disabled=$('#export-json').disabled=!data;
  if(data)$('#status').textContent=`${visible.length}개 표시 · ${historical?'과거 기록':'수집'} ${fullDate(data.fetched_at)} KST${state.hours===12&&!explore?' · 24시간 원본에서 필터링':''}`;
}
function warnings(){
  const notes=[];if(data){const age=Date.now()-Date.parse(data.fetched_at);if(!historical&&age>(state.view==='explore'?36:3)*3600000)notes.push('최신 수집이 지연되었습니다. 표시된 수집 시각을 확인하세요.');
    if(state.view==='trending'&&state.hours===12)notes.push('12시간은 수집 시점 기준 최근 12시간 이내 시작된 검색어입니다. 검색량·증가율은 24시간 원본 값입니다.');
    if(state.view==='explore'&&data.comparison_status!=='ok')notes.push('현재 검색어는 수집했지만 직전 기간 비교는 가져오지 못했습니다.');
  }
  const errors=(index?.errors||[]).filter(e=>e.geo===state.geo&&(state.view==='explore'?e.source.startsWith('explore')&&e.period===state.period:(e.source==='trending'&&e.hours===(state.hours===12?24:state.hours))||e.source==='news'));
  if(errors.length)notes.push('일부 수집 요청이 실패했습니다. 마지막 정상 결과를 표시하며 뉴스가 일부 없을 수 있습니다.');
  $('#warning').textContent=notes.join(' ');$('#warning').hidden=!notes.length;
}
async function load(){
  const id=++requestId;data=null;render();$('#refresh').disabled=true;$('#warning').hidden=true;$('#status').textContent='Google 트렌드 수집본을 불러오는 중입니다…';
  const path=state.view==='explore'?`explore/${state.geo}/${state.period}.json`:`latest/${state.geo}/${state.hours===12?24:state.hours}.json`;
  try{const [meta,body]=await Promise.all([json('index.json'),json(path)]);if(id!==requestId)return;index=meta;data=body;renderCategories();render();warnings();nextCheck=Date.now()+300000;openHash();}
  catch(error){if(id!==requestId)return;$('#status').textContent='데이터를 불러오지 못했습니다.';$('#warning').textContent=`${error.message} Google 원문을 이용하거나 잠시 후 새로고침하세요.`;$('#warning').hidden=false;}
  finally{if(id===requestId)$('#refresh').disabled=false;}
}
function resetHistory(){historical=false;snapshots=[];historyId++;$('#history').hidden=true;$('#history-toggle').setAttribute('aria-expanded','false');}
async function showHistory(){
  if(!index)return;const panel=$('#history');panel.hidden=!panel.hidden;$('#history-toggle').setAttribute('aria-expanded',String(!panel.hidden));if(panel.hidden)return;
  const select=$('#history-date');select.replaceChildren();
  for(const day of [...(index.history_days[state.geo]||[])].reverse()){const opt=el('option',day);opt.value=day;select.append(opt);}
  for(const file of [...(index.history_archives[state.geo]||[])].reverse()){const opt=el('option',`${file.slice(0,7)} · 압축 기록`);opt.value=file;select.append(opt);}
  if(!select.options.length){$('#history-time').textContent='저장된 기록 없음';return;}await loadHistory();
}
async function readHistory(value,geo){
  const file=value.endsWith('.gz')?value:`${value}.jsonl`;
  const response=await fetch(`./data/history/${geo}/${file}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});if(!response.ok)throw new Error('히스토리를 불러오지 못했습니다.');
  let text;if(file.endsWith('.gz')){if(!('DecompressionStream' in window))throw new Error('압축 기록을 보려면 최신 브라우저가 필요합니다.');text=await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text();}else text=await response.text();
  return text.trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
}
async function loadHistory(){
  const id=++historyId;const geo=state.geo;$('#history-time').textContent='불러오는 중…';$('#history-range').disabled=true;
  try{const items=await readHistory($('#history-date').value,geo);if(id!==historyId)return;snapshots=items.filter(x=>x.hours===(state.hours===12?24:state.hours)).sort((a,b)=>a.fetched_at.localeCompare(b.fetched_at));const slider=$('#history-range');slider.max=Math.max(0,snapshots.length-1);slider.value=slider.max;slider.disabled=!snapshots.length;if(snapshots.length)showSnapshot();else $('#history-time').textContent='이 기간의 기록 없음';}
  catch(error){if(id===historyId)$('#history-time').textContent=error.message;}
}
function unpack(snapshot){return {...snapshot,prev_keywords:[],previous_fetched_at:null,trends:snapshot.trends.map(t=>({keyword:t[0],volume:t[1],increase_pct:t[2],categories:t[3],started_at:t[4],ended_at:t[5],related:[],news:[]}))};}
function showSnapshot(){const snapshot=snapshots[Number($('#history-range').value)];if(!snapshot)return;requestId++;$('#refresh').disabled=false;historical=true;data=unpack(snapshot);$('#history-time').textContent=`${fullDate(snapshot.fetched_at)} KST`;renderCategories();render();warnings();}
function detailStat(label,value){const box=el('div');box.append(el('span',label),el('strong',value));return box;}
async function openDetail(item,fromHash=false){
  const explore=state.view==='explore';const keyword=explore?item.query:item.keyword;selectedKeyword=keyword;$('#detail-title').textContent=keyword;const body=$('#detail-body');body.replaceChildren();
  const stats=el('div',undefined,'detail-stats');stats.append(detailStat(explore?(state.type==='top'?'검색 관심도':'증가율'):'검색량',explore?(state.type==='top'?`${item.value} / 100`:item.is_breakout?'급등':`${fmt.format(item.value)}%`):volume(item.volume)),detailStat(explore?'분석 기간':'상태',explore?periods[state.period][0]:item.ended_at?'종료':'상승 중'),detailStat('수집 시각',date(data.fetched_at)));body.append(stats);
  if(!explore){body.append(el('p',`시작 ${fullDate(item.started_at)} · ${item.ended_at?`종료 ${fullDate(item.ended_at)}`:'현재 상승 중'} (KST)`,'muted'));const categories=item.categories.map(id=>index?.categories?.[id]||`기타 (${id})`);body.append(el('p',categories.join(' · '),'muted'));const chips=el('div',undefined,'related-chips');for(const word of item.related){const b=el('button',word);b.addEventListener('click',()=>{$('#detail').close();state.query=word;$('#search').value=word;updateUrl();render();});chips.append(b);}body.append(chips);}
  const links=el('div',undefined,'links');const q=encodeURIComponent(keyword);links.append(link('Google 검색 ↗',`https://www.google.com/search?q=${q}`),link('Google 뉴스 ↗',`https://news.google.com/search?q=${q}&hl=${state.geo==='KR'?'ko':state.geo==='JP'?'ja':'en'}&gl=${state.geo}`),link('트렌드 분석 ↗',`https://trends.google.co.kr/explore?geo=${state.geo}&q=${q}&date=${encodeURIComponent(explore?periods[state.period][1]:'now 7-d')}`));body.append(links);
  body.append(el('h3','관련 뉴스'));let articles=item.news||[];
  if(explore){try{const cache=await json(`news-cache/${state.geo}.json`);if(selectedKeyword!==keyword)return;articles=cache[keyword.normalize('NFKC').toLocaleLowerCase().trim().replace(/\s+/g,' ')]?.articles||[];}catch{/* News is optional. */}}
  if(!articles.length)body.append(el('p',historical?'과거 기록에는 뉴스가 포함되지 않습니다. 위 뉴스 검색에서 확인하세요.':'이 검색어에 수집된 기사가 없습니다. 위 Google 뉴스 링크에서 확인하세요.','muted'));
  for(const article of articles){const url=safeUrl(article.url);if(!url)continue;const card=el('article',undefined,'news-card');const content=el('div');content.append(link(article.title,url),el('p',`${article.source||'출처 미상'} · ${article.published_at?fullDate(article.published_at)+' KST':'발행 시각 미제공'}`),el('p',article.origin==='google-trends-rss'?'Google Trends가 연결한 기사':'Google 뉴스의 키워드 검색 결과'));card.append(content);const image=safeUrl(article.image);if(image){const img=el('img');img.src=image;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>img.remove());card.append(img);}body.append(card);}
  if(explore)body.append(el('p','뉴스는 최근 수집한 기사입니다. 탐색 분석 기간 전체를 대상으로 한 기사 목록이 아닙니다.','muted'));
  else{body.append(el('h3','수집 이력'));const chart=el('div');chart.append(el('p','최근 기록을 확인하는 중…','muted'));body.append(chart);renderKeywordHistory(chart,keyword);}
  if(!fromHash)history.replaceState(null,'',`${location.pathname}${location.search}#open=${encodeURIComponent(keyword)}`);
  if(!$('#detail').open)$('#detail').showModal();
}
async function renderKeywordHistory(target,keyword){
  try{let items=snapshots;if(!items.length){const days=(index?.history_days?.[state.geo]||[]).slice(-3);items=(await Promise.all(days.map(day=>readHistory(day,state.geo)))).flat();}const points=items.filter(x=>x.hours===(state.hours===12?24:state.hours)).map(x=>({time:x.fetched_at,row:x.trends.find(t=>t[0]===keyword)})).filter(x=>x.row).slice(-24);target.replaceChildren();if(!points.length){target.append(el('p','이 검색어의 관측 이력이 아직 없습니다.','muted'));return;}const bars=el('div',undefined,'history-bars');const max=Math.max(1,...points.map(x=>x.row[1]));for(const point of points){const bar=el('div',undefined,'history-bar');bar.append(el('b',volume(point.row[1])));const meter=el('meter');meter.min=0;meter.max=max;meter.value=point.row[1];meter.setAttribute('aria-label',`${date(point.time)} 검색량 ${volume(point.row[1])}`);bar.append(meter,el('span',date(point.time)));bars.append(bar);}target.append(bars,el('p','최대 최근 3일·24회 관측 구간값입니다. 기간별 검색량을 합산하지 않습니다.','muted'));}catch{target.replaceChildren(el('p','수집 이력을 불러오지 못했습니다.','muted'));}
}
function openHash(){if(!data)return;const p=new URLSearchParams(location.hash.slice(1));const word=p.get('open');if(!word)return;const items=state.view==='explore'?data[state.type]:trendList();const item=items.find(t=>(t.keyword||t.query)===word);if(item)openDetail(item,true);}
function csvCell(value){let text=String(value??'');if(/^[\s]*[=+@\-]/.test(text)||/^[\t\r\n]/.test(text))text=`'${text}`;return `"${text.replaceAll('"','""')}"`;}
function download(kind){if(!data)return;const explore=state.view==='explore';const metadata={source:explore?'google-explore':'google-trends',geo:state.geo,view:state.view,hours:explore?undefined:state.hours,source_hours:explore?undefined:data.hours,period:explore?state.period:undefined,type:explore?state.type:undefined,fetched_at:data.fetched_at,query:state.query,category:state.category,historical};let body,mime;
 if(kind==='json'){body=JSON.stringify({...metadata,items:visible},null,2);mime='application/json';}
 else{const header=explore?['검색어','순위','상대 점수 또는 증가율','표시값','급등','순위 변동','신규 진입','유형','국가','기간','비교 기간','비교 상태','수집 시각']:['검색어','검색량 하한','증가율 %','시작 UTC','종료 UTC','카테고리','관련 키워드','뉴스 URL','국가','조회 시간','원본 시간','수집 시각'];const rows=visible.map(t=>explore?[t.query,t.rank,t.value,t.label,t.is_breakout,t.rank_change,t.is_new,state.type,state.geo,state.period,data.compare,data.comparison_status,data.fetched_at]:[t.keyword,t.volume,t.increase_pct,t.started_at,t.ended_at,t.categories.map(id=>index.categories[id]||id).join(' / '),t.related.join(' / '),t.news.map(n=>n.url).join(' / '),state.geo,state.hours,data.hours,data.fetched_at]);body='\uFEFF'+[header,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n');mime='text/csv;charset=utf-8';}
 const url=URL.createObjectURL(new Blob([body],{type:mime}));const a=el('a');a.href=url;a.download=`trends-${state.geo}-${explore?state.period+'-'+state.type:state.hours+'h'}-${data.fetched_at.slice(0,10)}.${kind}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{state.view=b.dataset.view;resetHistory();updateUrl();configure();load();}));
document.querySelectorAll('[data-type]').forEach(b=>b.addEventListener('click',()=>{state.type=b.dataset.type;updateUrl();configure();render();}));
$('#geo').addEventListener('change',e=>{state.geo=e.target.value;state.category='all';resetHistory();updateUrl();configure();load();});
$('#search').addEventListener('input',e=>{state.query=e.target.value.trim();updateUrl();render();});$('#sort').addEventListener('change',render);$('#only-active').addEventListener('change',render);
$('#refresh').addEventListener('click',()=>{resetHistory();load();});$('#history-toggle').addEventListener('click',showHistory);$('#history-date').addEventListener('change',loadHistory);$('#history-range').addEventListener('input',showSnapshot);$('#back-live').addEventListener('click',()=>{resetHistory();load();});
$('#export-csv').addEventListener('click',()=>download('csv'));$('#export-json').addEventListener('click',()=>download('json'));
$('#detail-close').addEventListener('click',()=>$('#detail').close());$('#detail').addEventListener('close',()=>{selectedKeyword=null;history.replaceState(null,'',location.pathname+location.search);});
window.addEventListener('hashchange',openHash);
let theme;try{theme=localStorage.getItem('theme');}catch{}document.documentElement.dataset.theme=theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');$('#theme').addEventListener('click',()=>{const value=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=value;try{localStorage.setItem('theme',value);}catch{}});
setInterval(()=>{const seconds=Math.max(0,Math.ceil((nextCheck-Date.now())/1000));$('#countdown').textContent=historical?'과거 기록 보는 중':`다음 확인 ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;if(!document.hidden&&!historical&&!$('#refresh').disabled&&Date.now()>=nextCheck){nextCheck=Date.now()+300000;load();}},1000);
configure();updateUrl();load();
