"""FastAPI surface for the demo.

  POST /research   -> run the full verifiable-research pipeline
  GET  /           -> minimal single-page UI (report + scorecard)
  GET  /healthz    -> liveness

Run: uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import agent

app = FastAPI(title="Verifiable Deep Research")


class ResearchRequest(BaseModel):
    question: str
    effort: str = "standard"


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/research")
def do_research(req: ResearchRequest):
    return asdict(agent.run(req.question, effort=req.effort))


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


INDEX_HTML = """
<!doctype html><meta charset=utf-8>
<title>Verifiable Deep Research</title>
<style>
 body{font:16px/1.5 system-ui;margin:2rem auto;max-width:820px;color:#111}
 input,select,button{font:inherit;padding:.5rem}
 input{width:60%}
 .card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
 .grade{font-size:2rem;font-weight:700}
 .supported{color:#137333}.partial{color:#b06000}.unsupported{color:#c5221f}
 .method{color:#5f6368;font-size:.85rem;margin-top:.75rem}
 .tally{margin-top:.35rem}
 pre{white-space:pre-wrap}
</style>
<h1>Verifiable Deep Research</h1>
<p>Ask a research question. Get a cited report <em>and</em> a groundedness
scorecard. The open question in agent evals is how to trust the number.
This one shows you the number.</p>
<div>
 <input id=q placeholder="e.g. How has US venture funding for AI agents changed in 2025?">
 <select id=e><option>lite</option><option selected>standard</option><option>deep</option></select>
 <button id=btn onclick=go()>Research</button>
</div>
<div id=out></div>
<script>
async function go(){
 const q=document.getElementById('q').value, e=document.getElementById('e').value;
 const out=document.getElementById('out');
 const btn=document.getElementById('btn');
 btn.disabled=true;
 out.innerHTML='<p>Researching + verifying… (deep can take a few minutes)</p>';
 try{
 const r=await fetch('/research',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({question:q,effort:e})});
 if(!r.ok) throw new Error('HTTP '+r.status);
 const d=await r.json(); const s=d.scorecard;
 out.innerHTML=`
  <div class=card><div class=grade>Groundedness ${(s.groundedness*100).toFixed(0)}% · grade ${s.grade}</div>
   <div class=tally><span class=supported>${s.supported} supported</span> ·
   <span class=partial>${s.partial} partial</span> ·
   <span class=unsupported>${s.unsupported} unsupported</span>
   out of ${s.total_claims} claims judged</div>
   <div class=tally>citation density ${s.citation_density} sources/claim ·
   ${s.effort} effort · ${s.latency_s}s</div>
   <div class=method>Method: each claim is judged only against excerpts from
   the sources it actually cites, not against the whole retrieval blob. The
   percentage is the fully-supported rate across the ${s.total_claims} claims
   audited in this run, not a validated score for every sentence. Judging is
   served by Parasail at temperature 0, retried with backoff on overload,
   with Claude available as a fallback when Parasail is overloaded (the
   fallback is not temperature-pinned, so fallback runs are not controlled
   comparisons). Heuristic grade bands:
   A ≥ 90%, B ≥ 75%, C ≥ 60%, D below. Honest limitation: the judge is an LLM
   and is not yet human-validated (κ &gt; 0.70 on a held-out subset is the
   production step). Stability across trials, not just accuracy, is the number
   to report next.</div></div>
  <div class=card><h3>Report</h3><pre>${(d.content||'').replace(/</g,'&lt;')}</pre></div>
  <div class=card><h3>Claim-level audit</h3>${d.verdicts.map(v=>
    `<p class=${v.verdict}><b>${v.verdict}</b> (${v.confidence})${
      v.cited_sources&&v.cited_sources.length?` · cites [${v.cited_sources.join(', ')}]`:''
    } — ${v.claim.replace(/</g,'&lt;')}<br>
     <small>${(v.reason||'').replace(/</g,'&lt;')}</small></p>`).join('')}</div>
  <div class=card><h3>Sources</h3>${d.sources.map(x=>
    `<div><a href="${x.url}" target=_blank>${(x.title||x.url).replace(/</g,'&lt;')}</a></div>`).join('')}</div>`;
 }catch(err){
 const detail=err&&err.message?`<small>${String(err.message).replace(/</g,'&lt;')}</small>`:'';
 out.innerHTML=`<p>This run did not complete. Load a captured result or retry.</p>${detail}`;
 }finally{
 btn.disabled=false;
 }
}
</script>
"""
