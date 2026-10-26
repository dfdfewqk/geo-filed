# -*- coding: utf-8 -*-
"""Fetch last successful same-branch GeoField candidate from GitHub Actions.

CI ONLY. The artifact's own GitHub SHA-256 digest is verified byte-for-byte.
Nothing touches installed Windows runtimes or any private CAD/FEA data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import urllib.error

REPOSITORY="dfdfewqk/geo-filed"
WORKFLOW="ai-agent-regression.yml"
BRANCH="work/ai-agent-evidence"
ARTIFACT_RE=re.compile(r"^GeoField-.*-ONE-EXTRACT-NOT-FINAL$")


def api(url,token,binary=False):
    req=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "User-Agent":"GeoField-verified-release-lineage",
        "X-GitHub-Api-Version":"2022-11-28"})
    if binary:
        # GitHub returns a 302 to a short-lived external Actions storage URL.
        # Python's default redirect may forward Authorization to that host,
        # which rejects it with 401. Handle the hop without leaking the token.
        class NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,request,fp,code,msg,headers,newurl):
                return None
        opener=urllib.request.build_opener(NoCrossHostRedirect)
        try:
            with opener.open(req,timeout=40) as response:
                data=response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):
                raise
            redirect=error.headers.get("Location")
            url=urllib.parse.urlsplit(redirect or "")
            if (url.scheme!="https" or not url.hostname or
                not (url.hostname.endswith(".blob.core.windows.net") or
                     url.hostname.endswith(".githubusercontent.com") or
                     url.hostname.endswith(".actions.githubusercontent.com"))):
                raise RuntimeError("Untrusted GitHub artifact download redirect") from error
            redirected=urllib.request.Request(redirect,headers={
                "User-Agent":"GeoField-verified-release-lineage"})
            with urllib.request.urlopen(redirected,timeout=60) as response:
                data=response.read()
    else:
        with urllib.request.urlopen(req,timeout=40) as response:
            data=response.read()
    return data if binary else json.loads(data)


def fetch_prior(destination,token):
    base="https://api.github.com/repos/"+REPOSITORY
    query=urllib.parse.urlencode({
        "branch":BRANCH,"status":"success","event":"push","per_page":30})
    runs=api(base+"/actions/workflows/"+WORKFLOW+"/runs?"+query,token)
    for run in runs.get("workflow_runs",[]):
        if run.get("conclusion")!="success" or run.get("head_branch")!=BRANCH:
            continue
        artifacts=api(base+"/actions/runs/"+str(run["id"])+"/artifacts?per_page=100",token)
        for artifact in artifacts.get("artifacts",[]):
            name=artifact.get("name","")
            raw_digest=artifact.get("digest") or ""
            if (artifact.get("expired") or not ARTIFACT_RE.fullmatch(name) or
                not re.fullmatch(r"sha256:[0-9a-f]{64}",raw_digest)):
                continue
            data=api(base+"/actions/artifacts/"+str(artifact["id"])+"/zip",token,binary=True)
            actual=hashlib.sha256(data).hexdigest()
            if actual!=raw_digest.split(":",1)[1]:
                raise RuntimeError("GitHub published candidate artifact SHA-256 mismatch")
            destination=Path(destination)
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():raise FileExistsError("Prior candidate already exists")
            destination.write_bytes(data)
            return actual, run["id"], artifact["id"]
    raise RuntimeError("No successful trusted preceding GeoField Actions artifact; refuse a blind candidate build")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    token=os.environ.get("GITHUB_TOKEN")
    if not token or os.environ.get("GITHUB_REPOSITORY")!=REPOSITORY:
        raise RuntimeError("GitHub Actions repository authentication required")
    sha,run,artifact=fetch_prior(args.out,token)
    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as file:
            file.write("GF_PRIOR_CANDIDATE_ZIP="+str(args.out)+"\n")
            file.write("GF_PRIOR_CANDIDATE_SHA256="+sha+"\n")
            file.write("GF_REQUIRE_PRIOR_CANDIDATE=1\n")
    print("[PRIOR CI] Verified last successful GitHub candidate run",run,
          "artifact",artifact,"SHA256",sha,flush=True)


if __name__=="__main__":
    main()
