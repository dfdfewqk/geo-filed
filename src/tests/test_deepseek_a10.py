"""A10 DeepSeek real production function contract — NO external requests.

All provider responses are mock transports and temporary in-process HTTP
fakes. No real tokens, local STEP/FRD source files or paid calls are made.
"""
from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
import ast
import sqlite3
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from test_agent_llm import describe, status
from test_agent_evidence import agent, record, CAD, CASE, RUN

DEEPSEEK_KEY="test-deepseek-key-for-contract-only"
ENV={"GEOFIELD_AGENT_LLM_ENABLED":"1",
     "GEOFIELD_AGENT_LLM_PROVIDER":"deepseek",
     "DEEPSEEK_API_KEY":DEEPSEEK_KEY}


def evidence():
    return agent(*record())


def reply(text="검증된 실제 응력·변위는 구조 안전을 증명하지 않습니다."):
    return {"choices":[{"finish_reason":"stop","message":{"content":text}}]}


def test_official_supported_models_and_no_hidden_fallback():
    conf=status(ENV)
    assert conf["configured"] is True
    assert conf["provider"]=="deepseek"
    assert conf["selected_model"]=="deepseek-flash"
    assert conf["timeout_seconds"]==60
    assert conf["connected"] is False
    for model in ("deepseek-flash","deepseek-v4-pro"):
        c=status(dict(ENV,GEOFIELD_AGENT_LLM_MODEL=model))
        assert c["configured"] is True
        assert c["selected_model"]==model
    for stale in ("deepseek-chat","deepseek-reasoner","deepseek-v4-flash",
                  "test-model","deepseek-flash/../../other","","x"*81):
        if stale=="":
            continue # empty value chooses the documented default flash
        assert status(dict(ENV,GEOFIELD_AGENT_LLM_MODEL=stale))["configured"] is False
    assert status(dict(ENV,GEOFIELD_AGENT_LLM_PROVIDER="unknown"))["configured"] is False


@pytest.mark.parametrize("removed",[
    "GEOFIELD_AGENT_LLM_ENABLED","GEOFIELD_AGENT_LLM_PROVIDER",
    "DEEPSEEK_API_KEY"
])
def test_required_configuration_and_consented_provider(removed):
    env=dict(ENV)
    env.pop(removed)
    assert status(env)["configured"] is False or status(env)["provider"]!="deepseek"
    assert DEEPSEEK_KEY not in json.dumps(status(env))
    assert DEEPSEEK_KEY not in json.dumps(status(ENV))


def test_one_request_consent_is_required_even_with_key():
    sends=[]
    def fake(*args):
        sends.append(args)
        return reply()
    out=describe(evidence(),opt_in=False,environ=ENV,transport=fake)
    assert out["status"]=="rules_only"
    assert sends==[]
    assert out["executed"] is False


def test_deepseek_payload_only_contains_verified_numeric_allowlist():
    source=evidence()
    original=copy.deepcopy(source)
    captures=[]
    def fake(payload,key):
        captures.append((copy.deepcopy(payload),key))
        return reply()
    out=describe(source,opt_in=True,environ=ENV,transport=fake)
    assert source==original
    assert len(captures)==1
    data,key=captures[0]
    assert key==DEEPSEEK_KEY
    assert data["model"]=="deepseek-flash"
    assert data["thinking"]=={"type":"disabled"}
    assert data["max_tokens"]==220
    assert data["stream"] is False
    assert data["messages"][0]["role"]=="system"
    values=json.loads(data["messages"][1]["content"])
    assert set(values)=={
      "cad_measured_review_candidate_count","ml_status",
      "fea_status","fea_max_von_mises_mpa","fea_max_displacement_mm",
      "element_type","convergence","structural_safety_certified"
    }
    assert values["fea_max_von_mises_mpa"]==14.512
    assert values["fea_max_displacement_mm"]==0.05698
    raw=json.dumps(data)
    for value in (CAD,CASE,RUN,".step",".frd","C:\\Users\\","/mnt/data",
                  "DEEPSEEK_API_KEY",DEEPSEEK_KEY):
        assert value not in raw
    assert out["provider"]=="deepseek"
    assert out["status"]=="external_explanation_only"
    assert out["opt_in"] is True
    assert out["executed"] and out["connected"]
    assert out["cad_sha256"]==CAD
    assert out["case_sha256"]==CASE
    assert out["run_id"]==RUN
    assert out["evidence_bound"] is True
    assert out["persisted"] is False
    assert out["external_text_unverified"] is True


def test_injected_private_paths_and_untrusted_strings_never_sent():
    e=evidence()
    e["cad"]["findings_count"]="../secret/filename.step"
    e["fea"]["note"]="secret:/Users/real/private.frD"
    e["private_path"]="C:\\Secret\\.step"
    seen=[]
    def transport(payload,key):
        seen.append(json.dumps(payload))
        return reply()
    out=describe(e,opt_in=True,environ=ENV,transport=transport)
    assert out["status"]=="external_explanation_only"
    assert len(seen)==1
    for secret in ("../secret","private.frD","C:\\Secret"):
        assert secret not in seen[0]


def test_cad_only_llm_response_never_claims_fea_run_binding():
    parts=list(record())
    parts[4]={}
    parts[0]["fea"]={"state":"not_run"}
    a=agent(*parts)
    captures=[]
    def capture(payload,key):
        captures.append(json.loads(payload["messages"][1]["content"]))
        return reply("추가 FEA 검증이 필요합니다.")
    out=describe(a,opt_in=True,environ=ENV,transport=capture)
    assert captures[0]["fea_max_von_mises_mpa"] is None
    assert captures[0]["fea_max_displacement_mm"] is None
    assert out["run_id"] is None and out["case_sha256"] is None
    assert out["evidence_bound"] is False


class FakeHTTPResponse:
    status=200
    headers={"Content-Length":"150"}
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,limit):
        assert limit==48001
        return json.dumps(reply()).encode("utf-8")


def test_real_stdlib_transport_url_method_timeout_redirect_and_zero_retries():
    requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append((request,timeout))
            return FakeHTTPResponse()
    registered=[]
    def build(*handlers):
        registered.extend(handlers)
        return Opener()
    with patch("urllib.request.build_opener",side_effect=build):
        out=describe(evidence(),opt_in=True,environ=ENV)
    assert out["status"]=="external_explanation_only"
    assert len(requests)==1
    req,timeout=requests[0]
    assert timeout==60
    assert req.full_url=="https://api.deepseek.com/chat/completions"
    assert req.get_method()=="POST"
    assert DEEPSEEK_KEY in req.get_header("Authorization")
    assert len(registered)==1
    assert registered[0].redirect_request(None,None,None,None,None,None,None) is None
    payload=json.loads(req.data)
    assert payload["model"]=="deepseek-flash"


@pytest.mark.parametrize("code,expected",[
    (401,"authentication_failed"),(402,"insufficient_balance"),
    (403,"access_denied"),(404,"unsupported_model"),
    (408,"timeout"),(429,"rate_limited"),(500,"provider_error")
])
def test_specific_provider_error_classification_without_leaking_token(code,expected):
    calls=[]
    def fake(*args):
        calls.append(args)
        raise urllib.error.HTTPError("https://api.deepseek.com/chat/completions",
            code, "KEY="+DEEPSEEK_KEY,None,None)
    out=describe(evidence(),opt_in=True,environ=ENV,transport=fake)
    assert out["status"]==expected
    assert out["provider"]=="deepseek"
    assert out["retry_attempted"] is False
    assert out["connected"] is False
    assert len(calls)==1
    assert DEEPSEEK_KEY not in json.dumps(out)


@pytest.mark.parametrize("err,reason",[
    (TimeoutError("secret token"),"timeout"),
    (socket.timeout("socket key"),"timeout"),
    (urllib.error.URLError("network secret"),"network_unavailable"),
    (ValueError("malformed JSON"),"invalid_response"),
    (RuntimeError("key leaked in message"),"unavailable")
])
def test_network_and_parse_errors_cannot_leak_arbitrary_messages(err,reason):
    out=describe(evidence(),opt_in=True,environ=ENV,
                 transport=lambda *_:(_ for _ in ()).throw(err))
    assert out["status"]==reason
    assert out["connected"] is False
    assert "secret" not in json.dumps(out)
    assert "key leaked" not in json.dumps(out)


@pytest.mark.parametrize("invalid",[
    {},{"choices":[]},
    {"choices":[{"finish_reason":"length","message":{"content":"incomplete"}}]},
    {"choices":[{"finish_reason":"stop","message":{"content":""}}]},
    {"choices":[{"finish_reason":"stop","message":{"content":"x"*1601}}]}
])
def test_malformed_explanation_discarded(invalid):
    out=describe(evidence(),opt_in=True,environ=ENV,
                 transport=lambda *_:invalid)
    assert out["status"]=="invalid_response"
    assert out["explanation"] is None


def test_existing_openai_generic_configuration_does_not_break():
    from test_agent_llm import ENV as OLD_ENV
    conf=status(OLD_ENV)
    assert conf["provider"]=="openai"
    assert conf["configured"]
    assert conf["timeout_seconds"]==8


def test_frontend_explicit_deepseek_consent_and_timeout():
    source=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py").read_text()
    assert "self.headers.get('X-GeoField-LLM-Opt-In')=='1'" in source
    assert "gf_agent_assert_restore_session(session,current_session)" in source
    assert "r12_at_end=r128_r12_status(uid,sha)" in source
    frontend=(Path(__file__).resolve().parents[1]/"payload"/"frontend"/"cad.js").read_text()
    assert "['openai','deepseek'].includes(llm.provider)" in frontend
    assert "await get('/api/agent/evidence/'+expected+'?llm=1',70000" in frontend
    assert "if($('agentLLMOptIn'))$('agentLLMOptIn').checked=false" in frontend
    assert "'X-GeoField-LLM-Opt-In':'1'" in frontend


def bind_function():
    source=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py")
    tree=ast.parse(source.read_text(encoding="utf-8"))
    extracted=[n for n in tree.body if isinstance(n,ast.FunctionDef)
               and n.name=="gf_deepseek_bind_history"]
    assert len(extracted)==1
    env={}
    exec(compile(ast.Module(body=extracted,type_ignores=[]),str(source),"exec"),env)
    return env["gf_deepseek_bind_history"]


def test_verified_deepseek_reply_binds_only_to_exact_real_sqlite_snapshot(tmp_path):
    from test_agent_evidence import JOB
    binder=bind_function()
    explanation=describe(evidence(),opt_in=True,environ=ENV,
                         transport=lambda *_:reply())
    sid="6"*32
    task={"id":RUN,"cad_job_id":JOB,"cad_sha256":CAD,
          "case_sha256":CASE,"status":"complete","history_snapshot_id":sid}
    db=tmp_path/"test-private-archive.sqlite3"
    stored={"cad":{"sha256":CAD},
            "fea":{"state":"complete","result_run_id":RUN,
                   "result_case_sha256":CASE}}
    with sqlite3.connect(db) as cx:
        cx.execute("CREATE TABLE snapshots(id TEXT PRIMARY KEY,summary_json TEXT)")
        cx.execute("INSERT INTO snapshots VALUES (?,?)",(sid,json.dumps(stored)))
    def reread(path,id):
        with sqlite3.connect(path) as cx:
            r=cx.execute("SELECT summary_json FROM snapshots WHERE id=?",(id,)).fetchone()
            return json.loads(r[0]) if r else None
    bound=binder(explanation,task,CAD,CASE,db,reread)
    assert bound["history_binding"]=={
       "status":"verified_existing_snapshot","snapshot_id":sid}
    assert explanation.get("history_binding") is None
    assert bound["persisted"] is False
    with sqlite3.connect(db) as cx:
        count=cx.execute("SELECT count(*) FROM snapshots").fetchone()[0]
    assert count==1
    # Deletion or failure to find a saved row never invents a linkage.
    with sqlite3.connect(db) as cx:
        cx.execute("DELETE FROM snapshots WHERE id=?",(sid,))
    missing=binder(explanation,task,CAD,CASE,db,reread)
    assert missing["history_binding"]=={
       "status":"run_only_not_persisted","snapshot_id":None}


def test_rejected_stale_deepseek_record_never_linked_to_different_run():
    binder=bind_function()
    explanation=describe(evidence(),opt_in=True,environ=ENV,
                         transport=lambda *_:reply())
    task={"id":RUN,"cad_sha256":CAD,"case_sha256":CASE,
          "status":"complete","history_snapshot_id":"6"*32}
    with pytest.raises(ValueError,match="SQLite 기록"):
        binder(explanation,task,CAD,CASE,Path("/not-used"),
               lambda *args:{"cad":{"sha256":"0"*64},
                             "fea":{"state":"complete","result_run_id":RUN,
                                    "result_case_sha256":CASE}})
    with pytest.raises(ValueError,match="변경"):
        binder(explanation,dict(task,id="5"*32),CAD,CASE,None,
               lambda *_:None)


def test_final_report_binds_a10_only_after_stale_ml_fea_r12_session_checks():
    backend=(Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py").read_text()
    route=backend.split("if path.startswith('/api/agent/evidence/'):",1)[1].split(
        "if path.startswith('/api/integration/decision/'):",1)[0]
    assert route.index("r12_at_end=r128_r12_status(uid,sha)") < route.index(
        "response['llm']=gf_deepseek_bind_history(") < route.index("return self.send_raw(response)")


def test_provider_line_breaks_are_supported_but_control_bytes_blocked():
    approved=describe(evidence(),opt_in=True,environ=ENV,
                     transport=lambda *_:reply("첫 번째 확인.\n두 번째 확인.\t끝"))
    assert approved["status"]=="external_explanation_only"
    assert "\n" in approved["explanation"]
    bad=describe(evidence(),opt_in=True,environ=ENV,
                 transport=lambda *_:reply("bad"+chr(0)+"injection"))
    assert bad["status"]=="invalid_response"
