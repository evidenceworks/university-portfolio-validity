#!/usr/bin/env python3
"""Apply the archived rules for research-output eligibility and institutional attribution.

Decisions are SUPPORTED, EXCLUDED or UNRESOLVED.
"""
from __future__ import annotations
import csv, json, re, unicodedata
from datetime import date, datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent

_EQUIV={'univ':'university','dept':'department','sch':'school','inst':'institute','ctr':'center'}


def normalize_text(value):
    s=unicodedata.normalize('NFKC',str(value or '')).lower().replace('&',' and ')
    s=re.sub(r'[\u2010-\u2015\-_/]+',' ',s)
    s=re.sub(r"[^\w\s']+",' ',s,flags=re.UNICODE)
    toks=[_EQUIV.get(t,t) for t in s.split()]
    return ' '.join(toks)


def parse_date(value):
    if value is None or value=='': return None
    if isinstance(value,date): return value
    s=str(value).strip()
    for fmt in ('%Y-%m-%d','%Y-%m','%Y'):
        try:
            d=datetime.strptime(s,fmt).date()
            return d
        except ValueError: pass
    return None


def _active(row, work_date):
    vf=parse_date(row.get('valid_from')); vt=parse_date(row.get('valid_to'))
    if work_date is None:
        return not vf and not vt
    if vf and work_date<vf: return False
    if vt and work_date>vt: return False
    return True


def _ctx_ok(spec,text):
    if not spec: return True
    n=normalize_text(text)
    return any(normalize_text(x) in n for x in str(spec).split('|') if x.strip())


def _ctx_blocked(spec,text):
    if not spec: return False
    n=normalize_text(text)
    return any(normalize_text(x) in n for x in str(spec).split('|') if x.strip())


def _contains_alias(text,alias):
    nt,na=normalize_text(text),normalize_text(alias)
    if not nt or not na: return False
    return re.search(r'(?<!\w)'+re.escape(na)+r'(?!\w)',nt) is not None


def load_registry(path=None):
    path=Path(path or HERE/'boundary_registry_v2.csv')
    with path.open(newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def load_rules(path=None):
    path=Path(path or HERE/'eligibility_rules_v2.json')
    return json.loads(path.read_text(encoding='utf-8'))


def _work_id(work):
    return work.get('id') or work.get('work_openalex_id') or ''


def _work_date_source(work):
    d=parse_date(work.get('publication_date'))
    if d: return d,'DAY' if len(str(work.get('publication_date')))==10 else 'PARTIAL'
    y=work.get('publication_year')
    if y:
        try: return date(int(y),1,1),'YEAR_ONLY'
        except Exception: pass
    return None,'MISSING'


def _independent_date(evidence,rules):
    ev=evidence or {}
    allowed_order={k:i for i,k in enumerate(rules['date_precedence']) if k!='openalex_source'}
    disallowed=set(rules['disallowed_date_fallbacks'])
    candidates=[]
    ignored=[]
    for rec in ev.get('publication_dates',[]) or []:
        kind=rec.get('source_kind','')
        if kind in disallowed:
            ignored.append(kind); continue
        if rec.get('same_version') is False: continue
        if kind not in allowed_order: continue
        d=parse_date(rec.get('date'))
        if not d: continue
        candidates.append((allowed_order[kind],d,kind,rec))
    if not candidates: return None,ignored,None
    best=min(x[0] for x in candidates)
    top=[x for x in candidates if x[0]==best]
    years={x[1].year for x in top}
    if len(years)>1:
        return 'CONFLICT',ignored,top
    return min(top,key=lambda x:x[1])[1:],ignored,top


def _classify_timing(work,evidence,rules):
    source_date,source_precision=_work_date_source(work)
    independent,ignored,top=_independent_date(evidence,rules)
    start,end=rules['scientific_cohort']['start_year'],rules['scientific_cohort']['end_year']
    if independent=='CONFLICT':
        return {'status':'UNRESOLVED','confidence':'LOW','resolved_date':None,'date_precision':'CONFLICT','source_only':False,'reason':'Conflicting independent same-version publication years.','ignored_date_fields':ignored}
    if independent:
        d,kind,rec=independent
        status='SUPPORTED' if start<=d.year<=end else 'EXCLUDED'
        return {'status':status,'confidence':'HIGH','resolved_date':d.isoformat(),'date_precision':rec.get('precision') or ('YEAR_ONLY' if len(str(rec.get('date')))==4 else 'INDEPENDENT'),'source_only':False,'reason':f'Independent same-version publication date from {kind} overrides source date.','ignored_date_fields':ignored}
    if source_date:
        status='SUPPORTED' if start<=source_date.year<=end else 'EXCLUDED'
        return {'status':status,'confidence':'SOURCE_ONLY','resolved_date':source_date.isoformat(),'date_precision':source_precision,'source_only':True,'reason':'Only OpenAlex/source publication date available; retained as flagged source-only estimate.','ignored_date_fields':ignored}
    return {'status':'UNRESOLVED','confidence':'NONE','resolved_date':None,'date_precision':'MISSING','source_only':False,'reason':'No usable publication date; disallowed created/deposited/indexed/upload timestamps are not fallbacks.','ignored_date_fields':ignored}


def _classify_type(work,evidence,rules):
    ev=evidence or {}
    role=ev.get('explicit_nonresearch_role')
    if role in set(rules['explicit_nonresearch_roles']):
        return {'status':'EXCLUDED','confidence':'HIGH','resolved_type':role,'source_only':False,'reason':'Publication-specific evidence identifies an excluded nonresearch role.'}
    ext_type=ev.get('publication_type')
    if ext_type:
        ext=normalize_text(ext_type).replace(' ','-')
        if ext_type in rules['included_source_types'] or ext in rules['included_source_types'] or ext_type in set(rules.get('independent_research_type_aliases',[])) or ext in set(rules.get('independent_research_type_aliases',[])):
            return {'status':'SUPPORTED','confidence':'HIGH','resolved_type':ext_type,'source_only':False,'reason':'Independent publication-type evidence identifies a scholarly research output.'}
        if ext_type in rules['explicit_nonresearch_types'] or ext in rules['explicit_nonresearch_types']:
            return {'status':'EXCLUDED','confidence':'HIGH','resolved_type':ext_type,'source_only':False,'reason':'Independent publication-type evidence identifies a nonresearch item.'}
    title=str(work.get('title') or '')
    nt=normalize_text(title)
    for pat in rules['anchored_nonresearch_title_patterns']:
        if re.search(pat,nt,re.I):
            return {'status':'EXCLUDED','confidence':'MEDIUM','resolved_type':'title_pattern_nonresearch','source_only':False,'reason':f'Anchored nonresearch title pattern matched: {pat}'}
    src=work.get('type') or work.get('frozen_work_type') or work.get('work_type')
    mapped=rules['source_type_mapping'].get(src,src)
    if src in rules['included_source_types'] or mapped in rules['included_source_types']:
        return {'status':'SUPPORTED','confidence':'SOURCE_ONLY','resolved_type':mapped,'source_only':True,'reason':'Source type is in the frozen research-output mapping; no independent nonresearch contradiction supplied.'}
    if src:
        return {'status':'EXCLUDED','confidence':'SOURCE_ONLY','resolved_type':src,'source_only':True,'reason':'Source type is outside the frozen research-output mapping.'}
    return {'status':'UNRESOLVED','confidence':'NONE','resolved_type':None,'source_only':False,'reason':'No usable work type.'}


def _all_author_affiliations(work,evidence):
    out=[]
    for ai,a in enumerate(work.get('authorships') or []):
        aname=(a.get('author') or {}).get('display_name') or a.get('author_name') or f'author_{ai}'
        seen=set()
        for s in a.get('raw_affiliation_strings') or []:
            if s and s not in seen: out.append({'author':aname,'text':s,'source':'openalex_raw','context_role':'current_affiliation'}); seen.add(s)
        for x in a.get('affiliations') or []:
            s=x.get('raw_affiliation_string') if isinstance(x,dict) else None
            if s and s not in seen: out.append({'author':aname,'text':s,'source':'openalex_structured_raw','context_role':'current_affiliation'}); seen.add(s)
    for x in (evidence or {}).get('author_affiliations',[]) or []:
        if not x.get('text'): continue
        out.append({'author':x.get('author','external_author'),'text':x['text'],'source':x.get('source_kind','external_structured'),'context_role':x.get('context_role','current_affiliation')})
    return out


def _classify_affiliation(work,focal_id,evidence,registry,rules,work_date):
    ev=evidence or {}
    focal_rows=[r for r in registry if r.get('focal_openalex_id')==focal_id]
    pos_rows=[r for r in focal_rows if r.get('decision')=='SUPPORTED' and _active(r,work_date)]
    neg_rows=[r for r in focal_rows if r.get('decision')=='EXCLUDED' and _active(r,work_date)]
    affs=_all_author_affiliations(work,ev)
    role_patterns=[re.compile(p,re.I) for p in rules['author_role_noncurrent_patterns']]
    contaminated_norm={normalize_text(x) for x in (ev.get('role_contaminated_strings') or [])}
    positives=[]; negatives=[]; contaminated=[]; dangling=[]
    for rec in affs:
        text=rec['text']; nt=normalize_text(text)
        role=rec.get('context_role','current_affiliation')
        noncurrent=(role in {'biography_education','editor','reviewer','reference_list','prior_degree','noncurrent'}) or any(p.search(nt) for p in role_patterns) or any(c and c in nt for c in contaminated_norm)
        if noncurrent:
            contaminated.append({'author':rec['author'],'text':text,'source':rec['source'],'reason':role}); continue
        if re.search(r'(?:\band\b)\s*$',nt):
            dangling.append({'author':rec['author'],'text':text}); continue
        pm=[]; nm=[]
        for r in pos_rows:
            if _contains_alias(text,r['alias_text']) and _ctx_ok(r.get('required_context'),text) and not _ctx_blocked(r.get('excluded_context'),text):
                pm.append(r)
        for r in neg_rows:
            if _contains_alias(text,r['alias_text']) and _ctx_ok(r.get('required_context'),text): nm.append(r)
        clean=[]
        for p in pm:
            if p.get('entity_relation')=='INTERNAL_SUBUNIT':
                clean.append(p); continue
            blocked=False
            np=normalize_text(p.get('alias_text'))
            for n in nm:
                nn=normalize_text(n.get('alias_text'))
                if np and nn and np in nn:
                    blocked=True; break
            if not blocked: clean.append(p)
        if clean:
            positives.append({'author':rec['author'],'text':text,'source':rec['source'],'aliases':[p['alias_text'] for p in clean]})
        elif nm:
            negatives.append({'author':rec['author'],'text':text,'source':rec['source'],'entities':[n['alias_text'] for n in nm]})
    if positives:
        conf='HIGH' if any(x['source'].startswith('external') for x in positives) else 'MEDIUM'
        return {'status':'SUPPORTED','confidence':conf,'reason':'At least one author-level affiliation matches an active focal/historical/internal alias under the boundary registry.','positive_hits':positives,'negative_hits':negatives,'contaminated_hits':contaminated,'dangling_hits':dangling}
    if negatives:
        return {'status':'EXCLUDED','confidence':'HIGH','reason':'Publication-specific author affiliation identifies a known excluded neighboring/longer entity and no clean focal affiliation remains.','positive_hits':[],'negative_hits':negatives,'contaminated_hits':contaminated,'dangling_hits':dangling}
    if ev.get('affiliation_evidence_complete') and affs:
        return {'status':'EXCLUDED','confidence':'HIGH','reason':'Complete publication-specific author-affiliation evidence identifies nonfocal/currently contaminated affiliations and no focal alias.','positive_hits':[],'negative_hits':[],'contaminated_hits':contaminated,'dangling_hits':dangling}
    return {'status':'UNRESOLVED','confidence':'LOW' if affs else 'NONE','reason':'No clean focal author affiliation established; absence of evidence is not treated as exclusion.','positive_hits':[],'negative_hits':negatives,'contaminated_hits':contaminated,'dangling_hits':dangling}


def _classify_identity(work,evidence):
    ev=evidence or {}
    if ev.get('exact_version_identity') is False:
        return {'status':'EXCLUDED','confidence':'HIGH','reason':'Independent evidence contradicts exact work/version identity.'}
    if ev.get('exact_version_identity') is True:
        return {'status':'SUPPORTED','confidence':'HIGH','reason':'Independent publication-specific evidence verifies the exact work/version identity.'}
    if _work_id(work) and (work.get('title') or work.get('doi')):
        return {'status':'SUPPORTED','confidence':'SOURCE_ONLY','reason':'OpenAlex/source work identity is internally specified; independent validation remains an audit facet.'}
    return {'status':'UNRESOLVED','confidence':'LOW','reason':'Insufficient source identity fields.'}


def classify(work,focal_openalex_id,evidence=None,registry_path=None,rules_path=None):
    rules=load_rules(rules_path); registry=load_registry(registry_path)
    timing=_classify_timing(work,evidence,rules)
    wd=parse_date(timing.get('resolved_date')) or _work_date_source(work)[0]
    identity=_classify_identity(work,evidence)
    typ=_classify_type(work,evidence,rules)
    aff=_classify_affiliation(work,focal_openalex_id,evidence,registry,rules,wd)
    facets={'identity':identity,'type':typ,'timing':timing,'affiliation':aff}
    statuses=[x['status'] for x in facets.values()]
    if 'EXCLUDED' in statuses: final='EXCLUDED'
    elif all(x=='SUPPORTED' for x in statuses): final='SUPPORTED'
    else: final='UNRESOLVED'
    return {
        'classification':final,
        'identity_confidence':identity['confidence'],
        'type_confidence':typ['confidence'],
        'timing_confidence':timing['confidence'],
        'affiliation_confidence':aff['confidence'],
        'source_only_date':bool(timing.get('source_only')),
        'source_only_type':bool(typ.get('source_only')),
        'facets':facets,
        'rule_version':rules['version']
    }


def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('work_json'); ap.add_argument('focal_openalex_id')
    ap.add_argument('--evidence-json'); ap.add_argument('--registry'); ap.add_argument('--rules')
    ns=ap.parse_args()
    work=json.loads(Path(ns.work_json).read_text(encoding='utf-8'))
    evidence=json.loads(Path(ns.evidence_json).read_text(encoding='utf-8')) if ns.evidence_json else {}
    print(json.dumps(classify(work,ns.focal_openalex_id,evidence,ns.registry,ns.rules),indent=2,ensure_ascii=False))

if __name__=='__main__': main()
