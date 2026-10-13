import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// Tiny deterministic DOM adapter tests rendering behavior, not a substitute for the live browser gate.
class Element {
  constructor(tag) { this.tagName=tag;this.children=[];this.textContent='';this.listeners={};this.hidden=false; }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  addEventListener(name,fn){this.listeners[name]=fn;}
  scrollIntoView(){}
  get allText(){return this.textContent+this.children.map(x=>x.allText).join(' ');}
}
const ids=new Map();
globalThis.SEARCH_LAB_TEST=true;
globalThis.document={createElement:tag=>new Element(tag),getElementById:id=>{if(!ids.has(id))ids.set(id,new Element('div'));return ids.get(id);}};
const {renderCards,renderCase}=await import('../search_lab/static/app.js');

test('empty results explicitly say no matches',()=>{
  const target=new Element('div');renderCards(target,[]);
  assert.match(target.allText,/No matching records/);
});
test('source rendering uses text nodes, not HTML; button selects provenance',()=>{
  const target=new Element('div');
  renderCards(target,[{score:.83,document:{_id:'x',title:'<script>alert(1)</script>',text:'Original text',category:'office',region:'north',price:1,source:'Self-authored',license:'MIT'}}]);
  assert.match(target.allText,/not confidence/);
  assert.match(target.allText,/<script>/);
  assert.equal(target.children[0].children[1].tagName,'h3');
  const button=target.children[0].children.at(-1);button.listeners.click();
  assert.match(document.getElementById('source').textContent,/License: MIT/);
});
test('evaluation distinguishes no-answer from exact recall and displays actual n',()=>{
  const metrics={keyword:{label_recall_at_k:null,returned_on_no_answer:0},vector:{label_recall_at_k:null,returned_on_no_answer:3,exact_reference_recall_at_k:1},hybrid:{label_recall_at_k:null,returned_on_no_answer:3}};
  const latency={keyword:{median_ms:12,p95_ms:17,n:3,first_observed_ms:29},vector:{median_ms:13,p95_ms:18,n:3,first_observed_ms:30}};
  const result=renderCase({case:{id:'q7',text:'No medicine',relevant:[]},k:3,metrics,latency,conditions:'Server cache unknown'});
  assert.match(result.allText,/recall is undefined/);assert.match(result.allText,/n=3 warm/);assert.match(result.allText,/vector \/ exact recall@3: 1.000/);
});
test('HTML has labels for every query control and accessible progress/error',()=>{
  const html=readFileSync(new URL('../search_lab/static/index.html',import.meta.url),'utf8');
  for(const id of ['preset','index','query','category','region','k','mode'])assert.match(html,new RegExp(`label for="${id}"`));
  assert.match(html,/role="alert"/);assert.match(html,/aria-label="Evaluation case progress"/);
  const js=readFileSync(new URL('../search_lab/static/app.js',import.meta.url),'utf8');
  assert.doesNotMatch(js,/innerHTML|Math.random/);assert.match(js,/Partial results only/);
});
