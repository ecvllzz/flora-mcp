'use strict';
const $ = id => document.getElementById(id);
const form = $('search-form');
let catalog, criteria = {}, cursors = [null], page = 0, next = null, busy = false, toastTimer;
const number = n => Number(n).toLocaleString('pt-BR');
const date = s => s ? s.split('-').reverse().join('/') : 'não informada';
const node = (tag, className, text) => { const el = document.createElement(tag); if(className) el.className=className; if(text!==undefined) el.textContent=text; return el; };
let theme='dark';try{theme=localStorage.getItem('flora-jurisprudencia-theme')||'dark'}catch{}
function applyTheme(){document.documentElement.dataset.theme=theme;$('theme').textContent=theme==='dark'?'Tema claro':'Tema escuro'}
applyTheme();$('theme').addEventListener('click',()=>{theme=theme==='dark'?'light':'dark';applyTheme();try{localStorage.setItem('flora-jurisprudencia-theme',theme)}catch{}});
function toast(text,error=false){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').classList.toggle('error',error);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4000)}
async function api(path, values){
 const response=await fetch(path, values===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values),cache:'no-store'});
 let result;try{result=await response.json()}catch{throw new Error('Resposta indisponível. Tente atualizar a consulta.')}
 if(!response.ok){const error=new Error(result.mensagem||'Não foi possível consultar o acervo.');error.code=result.codigo;throw error}return result;
}
function choices(select,values,label){const previous=select.value;select.replaceChildren(new Option(label,''));for(const v of [...new Set(values)].filter(Boolean).sort((a,b)=>a.localeCompare(b,'pt-BR')))select.add(new Option(v,v));if([...select.options].some(o=>o.value===previous))select.value=previous}
function qualified(){return $('collection').value==='precedentes'}
function filters(){if(!catalog)return;const court=$('court').value;const groups=qualified()?(catalog.precedentes||[]):catalog.grupos;choices($('organ'),groups.filter(g=>!court||g.tribunal===court).map(g=>g.orgao),'Todos');choices($('class'),catalog.classes.filter(g=>!court||g.tribunal===court).map(g=>g.classe),'Todas');$('precedent-filters').hidden=!qualified();$('stf-option').hidden=!qualified();for(const name of ['classe','relator','processo','tipo_data'])form.elements.namedItem(name).closest('label').hidden=qualified();if(!qualified()&&$('court').value==='STF')$('court').value=''}
$('collection').addEventListener('change',()=>{filters();$('term-label').textContent=qualified()?'Palavras no componente':'Palavras na ementa';startSearch()});
$('court').addEventListener('change',filters);
async function loadCatalog(){catalog=await api('/api/catalog');const counts={STJ:0,TJSC:0};for(const g of catalog.grupos)counts[g.tribunal]=(counts[g.tribunal]||0)+g.documentos;$('total').textContent=number(counts.STJ+counts.TJSC);$('stj').textContent=number(counts.STJ);$('tjsc').textContent=number(counts.TJSC);$('collection-date').textContent=catalog.ultima_coleta?'Última coleta registrada: '+new Date(catalog.ultima_coleta).toLocaleString('pt-BR')+'. As fontes podem ter datas de atualização diferentes.':'Nenhuma coleta registrada.';filters()}
function pending(d){return d.referencia_completa===false?'Dados a conferir na fonte: '+d.referencia_pendencias.join(', ')+'.':''}
async function copy(text){
 try{if(!navigator.clipboard?.writeText)throw new Error('clipboard');await navigator.clipboard.writeText(text);toast('Texto copiado.')}catch{$('copy-text').value=text;$('copy-dialog').showModal();$('copy-text').focus();$('copy-text').select()}
}
function resultCard(d){
 if(d.componentes)return precedentCard(d);
 const article=node('article','result'),top=node('div','result-top');
 top.append(node('div','result-kicker',d.tribunal+' · '+d.orgao+' · '+date(d.data_publicacao)),node('h3','',d.classe+' n. '+d.numero_processo),node('p','reference',d.referencia));
 if(pending(d))top.append(node('p','warning',pending(d)));
 const preview=node('p','preview',d.ementa);top.append(preview);article.append(top);
 const actions=node('div','result-actions'),read=node('button','read','Ler ementa ↓'),copyAll=node('button','','Copiar ementa + referência'),copyRef=node('button','','Copiar referência');
 const content=node('div','result-content');content.hidden=true;content.id='ementa-'+d.id.replace(/[^a-z0-9]/gi,'-');
 read.type=copyAll.type=copyRef.type='button';read.setAttribute('aria-expanded','false');read.setAttribute('aria-controls',content.id);
 read.addEventListener('click',()=>{content.hidden=!content.hidden;preview.hidden=!content.hidden;read.textContent=content.hidden?'Ler ementa ↓':'Recolher ementa ↑';read.setAttribute('aria-expanded',String(!content.hidden))});
 copyAll.addEventListener('click',()=>copy(d.ementa+'\n\n'+d.referencia+(pending(d)?'\n\n'+pending(d):'')));
 copyRef.addEventListener('click',()=>copy(d.referencia+(pending(d)?'\n\n'+pending(d):'')));
 actions.append(read,copyAll,copyRef);
 if(d.url_documento){try{const url=new URL(d.url_documento);if(url.protocol==='https:'&&['eprocwebcon.tjsc.jus.br','dadosabertos.web.stj.jus.br'].includes(url.hostname)){const link=node('a','','Fonte oficial ↗');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';actions.append(link)}}catch{}}
 content.append(node('p','ementa',d.ementa),node('div','provenance','ID '+d.id+' · versão '+d.hash_conteudo+'\nEmenta recebida da fonte. A referência é apresentada separadamente.'));
 article.append(actions,content);return article;
}
function precedentCard(d){
 const article=node('article','result'),top=node('div','result-top');
 const species={sumula:'Súmula',sumula_vinculante:'Súmula vinculante',iac:'IAC',tema_repetitivo:'Tema repetitivo',tema_repercussao_geral:'Tema de repercussão geral'};
 top.append(node('div','result-kicker',d.tribunal+' · '+d.orgao+' · '+date(d.data_publicacao)),node('h3','',(species[d.especie]||d.especie)+' n. '+d.numero),node('p','reference',d.referencia),node('p','provenance','Situação conhecida: '+d.situacao));article.append(top);
 const labels={enunciado:'Enunciado',questao_submetida:'Questão submetida',tese_firmada:'Tese firmada',modulacao:'Modulação',suspensao:'Suspensão'};
 for(const [key,text] of Object.entries(d.componentes)){
  const section=node('div','result-content');section.append(node('h3','',labels[key]||key),node('p','ementa',text));
  const button=node('button','','Copiar '+(labels[key]||key)+' + referência');button.type='button';button.addEventListener('click',()=>copy((labels[key]||key)+'\n\n'+text+'\n\n'+d.referencia));section.append(button);article.append(section);
 }
 for(const judgment of d.julgados_relacionados||[]){const section=node('div','result-content');section.append(node('h3','','Julgado relacionado'),node('p','reference',judgment.referencia),node('p','ementa',judgment.ementa||'Ementa não disponível neste pacote.'));article.append(section)}
 const sources=node('div','result-actions');for(const source of d.fontes||[]){try{const url=new URL(source.url),domain=d.tribunal.toLowerCase()+'.jus.br';if(url.protocol==='https:'&&(url.hostname===domain||url.hostname.endsWith('.'+domain))){const link=node('a','','Fonte oficial ↗');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';sources.append(link,node('span','provenance','Coleta: '+new Date(source.coletado_em).toLocaleString('pt-BR')))}}catch{}}article.append(sources);return article;
}
function controls(){for(const el of form.elements)el.disabled=busy;$('refresh').disabled=busy;$('previous').disabled=busy||page===0;$('next').disabled=busy||!next;$('results').setAttribute('aria-busy',String(busy))}
async function search(target=0){
 if(busy)return;busy=true;controls();$('message').hidden=true;$('result-count').textContent='Pesquisando…';$('results').replaceChildren();
 try{
  const result=await api('/api/search',{...criteria,cursor:cursors[target]||null});
  page=target;next=result.proximo_cursor;
  $('results').replaceChildren(...result.resultados.map(resultCard));
  if(!result.resultados.length)$('results').append(node('div','empty','Nenhum documento encontrado neste acervo. Tente outros termos ou reduza os filtros.'));
  $('result-count').textContent=number(result.total_encontrado)+' '+(result.total_encontrado===1?'registro encontrado':'registros encontrados');
  $('page').textContent='Página '+(page+1)+' de '+Math.max(1,Math.ceil(result.total_encontrado/5));
  $('read-stamp').textContent='LEITURA '+new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})+' · REV. '+result.revisao_base;
  if(catalog&&catalog.revisao!==result.revisao_base)await loadCatalog();
 }catch(error){$('message').textContent=error instanceof TypeError?'O painel não está respondendo. Abra o atalho “Jurisprudência Flora” e tente novamente.':error.message;$('message').hidden=false;
  if(error.code==='base_alterada'){cursors=[null];page=0;next=null;$('message').textContent+=' Clique em Pesquisar para obter a versão atual.'}
 }finally{busy=false;controls()}
}
async function startSearch(refresh=false){if(busy)return;criteria=Object.fromEntries([...new FormData(form)].map(([k,v])=>[k,String(v).trim()]).filter(([,v])=>v));cursors=[null];page=0;next=null;
 if(qualified()){for(const key of ['classe','processo','relator','tipo_data'])delete criteria[key]}else{for(const key of ['campo','especie','numero'])delete criteria[key]}
 if(criteria.ordenar==='relevancia'&&!criteria.termos){$('message').textContent='Informe palavras na ementa para ordenar por relevância textual.';$('message').hidden=false;controls();return}
 try{if(refresh)await loadCatalog();await search(0)}catch{$('message').textContent='Não foi possível atualizar. Confira se o painel está iniciado.';$('message').hidden=false}}
form.addEventListener('submit',e=>{e.preventDefault();startSearch()});$('refresh').addEventListener('click',()=>startSearch(true));
$('clear').addEventListener('click',()=>{form.reset();filters();startSearch()});
$('previous').addEventListener('click',()=>search(page-1));$('next').addEventListener('click',()=>{cursors[page+1]=next;search(page+1)});
(async()=>{try{await loadCatalog();await startSearch()}catch{$('result-count').textContent='Acervo indisponível';$('message').textContent='Não foi possível ler a base. Inicie o painel pelo atalho “Jurisprudência Flora”.';$('message').hidden=false;$('results').setAttribute('aria-busy','false')}})();
