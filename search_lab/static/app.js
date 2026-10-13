const $ = (id) => document.getElementById(id);
let config;
let lastResults;
export function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
export function renderCards(target, rows) {
  target.replaceChildren();
  if (!rows.length) { target.append(node('p', 'No matching records. Nothing substituted.', 'hint')); return; }
  rows.forEach((row, i) => {
    const d = row.document;
    const card = node('div', undefined, 'card');
    card.append(node('div', `${d.category} / ${d.region} · $${d.price}`, 'meta'));
    card.append(node('h3', `${i + 1}. ${d.title}`), node('p', d.text));
    card.append(node('p', `Rank score ${row.score.toFixed(5)} · not confidence`, 'score'));
    const button = node('button', 'Inspect source'); button.type = 'button';
    button.addEventListener('click', () => {
      $('source-panel').hidden = false;
      $('source').textContent = `${d.title}\n${d.text}\n\nID: ${d._id}\nSource: ${d.source}\nLicense: ${d.license}`;
      $('source-panel').scrollIntoView({behavior: 'smooth', block: 'nearest'});
    });
    card.append(button); target.append(card);
  });
}
async function request(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json','X-Search-Lab':'same-origin'},body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Invalid request; check the query and filters.');
  return data;
}
function busy(value) { $('search-button').disabled=value; $('evaluate').disabled=value; }
function showResults() {
  if (!lastResults) return;
  for (const mode of ['keyword','vector','hybrid']) renderCards($(`${mode}-results`), lastResults[mode]);
  const hybrid = $('mode').value === 'hybrid';
  $('hybrid-panel').hidden = !hybrid;
  $('results').classList.toggle('with-hybrid', hybrid);
}
export function renderCase(result) {
  const section = node('article', undefined, 'case');
  section.append(node('h3', `${result.case.id.toUpperCase()} · ${result.case.text}`));
  section.append(node('p', result.case.relevant.length ? `Explicit relevant IDs: ${result.case.relevant.join(', ')}` : 'Explicit no-answer case · recall is undefined.', result.case.relevant.length ? 'hint' : 'no-answer'));
  const metrics = node('div', undefined, 'metrics');
  for (const mode of ['keyword','vector','hybrid']) {
    const m=result.metrics[mode];
    const score = m.label_recall_at_k === null ? `no-answer returned: ${m.returned_on_no_answer}` : `label recall@${result.k}: ${m.label_recall_at_k.toFixed(3)}`;
    metrics.append(node('div', `${mode}: ${score}`, 'metric'));
  }
  metrics.append(node('div', `vector / exact recall@${result.k}: ${result.metrics.vector.exact_reference_recall_at_k.toFixed(3)}`, 'metric'));
  section.append(metrics);
  for (const mode of ['keyword','vector']) {
    const l=result.latency[mode];
    section.append(node('p', `${mode} · median ${l.median_ms.toFixed(1)} ms · p95 ${l.p95_ms.toFixed(1)} ms · n=${l.n} warm · first-observed ${l.first_observed_ms.toFixed(1)} ms`, 'hint'));
  }
  section.append(node('p', result.conditions, 'hint'));
  return section;
}
export async function init() {
  try {
    config=await request('/api/config');
    config.queries.forEach(q => { const o=node('option',q.text);o.value=q.id;$('preset').append(o); });
    for (const key of ['category','region']) config[key==='category'?'categories':'regions'].forEach(v=>{const o=node('option',v);o.value=v;$(key).append(o);});
    $('preset').value='q1'; $('query').value=config.queries[0].text;
  } catch (e) { $('error').textContent=e.message;$('error').hidden=false; }
  $('preset').addEventListener('change',()=>{const q=config?.queries.find(x=>x.id===$('preset').value);if(q)$('query').value=q.text;});
  $('query').addEventListener('input',()=>{$('preset').value='';});
  $('mode').addEventListener('change',showResults);
  $('search-form').addEventListener('submit', async event=>{
    event.preventDefault();busy(true);$('error').hidden=true;$('status').textContent='Querying managed Azure DocumentDB…';
    lastResults=null;
    for(const mode of ['keyword','vector','hybrid']) $(`${mode}-results`).replaceChildren();
    $('source-panel').hidden=true;
    try {
      lastResults=await request('/api/search',{text:$('query').value,category:$('category').value||null,region:$('region').value||null,k:Number($('k').value),index:$('index').value});
      showResults();$('inspection').textContent=JSON.stringify(lastResults.inspection,null,2);
      $('status').textContent=`Live service response · keyword ${lastResults.latency_ms.keyword.toFixed(1)} ms · vector ${lastResults.latency_ms.vector.toFixed(1)} ms. Single-request timings, not a benchmark.`;
    } catch(e){$('error').textContent=e.message;$('error').hidden=false;$('status').textContent='Request failed. No static or stale results displayed.';$('inspection').textContent='No successful request to inspect.';}
    finally{busy(false);}
  });
  $('evaluate').addEventListener('click',async()=>{
    busy(true);$('error').hidden=true;$('eval-results').replaceChildren();$('progress').value=0;
    const k=Number($('k').value);
    try{
      for(const [i,q] of config.queries.entries()){
        $('eval-status').textContent=`Running ${i+1} / ${config.queries.length}: ${q.id}…`;
        const result=await request('/api/evaluate-case',{case_id:q.id,k,repeats:3});
        $('eval-results').append(renderCase(result));$('progress').value=i+1;
      }
      $('eval-status').textContent='Complete · 8/8 cases · measured service requests, no generated timings.';
    }catch(e){$('error').textContent=e.message;$('error').hidden=false;$('eval-status').textContent=`Stopped after ${$('progress').value}/8 cases. Partial results only; not a successful evaluation.`;}
    finally{busy(false);}
  });
}
if (typeof document !== 'undefined' && !globalThis.SEARCH_LAB_TEST) init();
