"""Sampling, operational contrasts and source sensitivities in the fixed frame."""
from collections import Counter,defaultdict
from fractions import Fraction
import copy,csv,gzip,hashlib,heapq,json,math,statistics
from common import DATA,CONFIGS,MAIN_RULES,NAMES,cases,load,prepare,fingerprint,write_csv,write_json
import resolver

Z975=1.959963984540054

def selection_check():
    historical=load('historical');institutional=load('institutional');seed=json.loads((DATA/'seed.json').read_text())['seed']
    exclusions=set(historical['excluded_work_ids']);studied={r['work_id'] for r in cases()}|set(historical['earlier_examined_work_ids'])
    old_heaps=defaultdict(list);new_heaps=defaultdict(list);retained_counts=Counter();remainder_counts=Counter();degrees=Counter();remainder_degrees=Counter();removals=Counter();seen=set();sampled=set(institutional['incidence']);incidence=defaultdict(set)
    with gzip.open(DATA/'frame.csv.gz','rt',encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            iid,wid=row['focal_openalex_id'],row['work_openalex_id'];assert (iid,wid) not in seen;seen.add((iid,wid));degrees[wid]+=1
            if wid in exclusions:removals['historical_excluded_pairs']+=1;continue
            retained_counts[iid]+=1
            h=hashlib.sha256(f"C09_DENOM_V2_FINAL_2026-09-16|{iid}|{wid}".encode()).hexdigest();v=(-int(h,16),wid)
            if len(old_heaps[iid])<8:heapq.heappush(old_heaps[iid],v)
            elif v>old_heaps[iid][0]:heapq.heapreplace(old_heaps[iid],v)
            if wid in studied:removals['previously_examined_pairs']+=1;continue
            remainder_counts[iid]+=1;remainder_degrees[wid]+=1
            if wid in sampled:incidence[wid].add(iid)
            h=hashlib.sha256(f'{seed}|{iid}|{wid}'.encode()).hexdigest();v=(-int(h,16),wid)
            if len(new_heaps[iid])<40:heapq.heappush(new_heaps[iid],v)
            elif v>new_heaps[iid][0]:heapq.heapreplace(new_heaps[iid],v)
    selected={(i,w) for i,heap in old_heaps.items() for _,w in heap}
    assert selected=={(r['institution_id'],r['work_id']) for r in cases()}
    assert retained_counts==Counter({r['institution_id']:int(r['candidate_count']) for r in historical['institutions']})
    actual=[]
    for iid in sorted(new_heaps):
        for rank,(h,wid) in enumerate(sorted(new_heaps[iid],reverse=True),1):actual.append((iid,wid,rank,remainder_counts[iid],f'{-h:064x}'))
    expected=[(r['institution_id'],r['work_id'],int(r['rank']),int(r['N']),r['selection_hash']) for r in institutional['sample']]
    assert actual==expected
    assert {w:set(ids) for w,ids in institutional['incidence'].items()}==dict(incidence)
    assert len(seen)==1045601 and len(degrees)==993732 and sum(remainder_counts.values())==1044517 and len(remainder_degrees)==992778
    assert removals=={'historical_excluded_pairs':407,'previously_examined_pairs':677}
    assert sum(Fraction(n,n) for n in remainder_degrees.values())==992778
    return dict(original_pairs=len(seen),original_distinct_ids=len(degrees),shared_original_ids=sum(n>1 for n in degrees.values()),original_pairs_on_shared_ids=sum(n for n in degrees.values() if n>1),retained_historical_pairs=sum(retained_counts.values()),target_pairs=sum(remainder_counts.values()),target_distinct_ids=len(remainder_degrees),removals=dict(removals),historical_selections_verified=400,institutional_selections_verified=2000,complete_sample_incidence_verified=2000,stratum_min=min(remainder_counts.values()),stratum_max=max(remainder_counts.values()))

def evaluate():
    data=load('institutional');sample=data['sample'];works=data['works'];incidence=data['incidence'];crossref={}
    for wid,w in works.items():
        doi=(w.get('doi') or '').replace('https://doi.org/','').lower()
        crossref[wid]=data['crossref'].get(doi,{'publication_dates':[],'author_affiliations':[]})
    pairs=sorted((iid,wid) for wid,ids in incidence.items() for iid in ids);network={(i,w):{'institution_id':i,'work_id':w} for i,w in pairs}
    for environment in ['none','crossref']:
        for config in CONFIGS:
            fn=prepare(config)
            for iid,wid in pairs:network[iid,wid][environment+'_'+config]=int(fn(works[wid],iid,crossref[wid] if environment=='crossref' else {})['classification']=='SUPPORTED')
    rows=[]
    for r in sample:
        wid=r['work_id'];w=works[wid];ev=crossref[wid];current=any(r['institution_id']==i['id'] for a in w.get('authorships',[]) for i in a.get('institutions',[]))
        rows.append(dict(r,**{k:v for k,v in network[r['institution_id'],wid].items() if k not in r},degree=len(incidence[wid]),canonical_id=w['id'],redirect=int(w['id']!=wid),doi=w.get('doi') or '',title=w.get('title') or '',type=w.get('type'),date=w.get('publication_date'),crossref_exact=int(ev.get('exact_version_identity',False)),crossref_affiliations=len(ev['author_affiliations']),current_focal=int(current)))
    matrix=[[i,w,environment,config,network[i,w][environment+'_'+config]] for i,w in pairs for environment in ['none','crossref'] for config in CONFIGS]
    return rows,network,crossref,fingerprint(matrix)

def estimate(groups,values,design='pilot_conditioned'):
    total=variance=Fraction()
    for iid,g in groups.items():
        N=int(g[0]['N'])
        if design=='pilot_conditioned':
            total+=sum(values[r['case_id']] for r in g if int(r['rank'])<=10);y=[values[r['case_id']] for r in g if int(r['rank'])>10];M,n=N-10,30
        else:y=[values[r['case_id']] for r in g];M,n=N,40
        z=sum(y);z2=sum(v*v for v in y);total+=Fraction(M,n)*z;variance+=Fraction(M*(M-n),n*(n-1))*(z2-z*z/n)
    point=float(total);se=math.sqrt(float(variance))
    return dict(estimate=point,se=se,normal95_lower=point-Z975*se,normal95_upper=point+Z975*se,exact_numerator=total.numerator,exact_denominator=total.denominator)

def operational_estimates(rows,network):
    groups=defaultdict(list)
    for r in rows:groups[r['institution_id']].append(r)
    incidence=load('institutional')['incidence'];values={};estimates=[];sources=[];identity=[];zeros=[]
    for env in ['none','crossref']:
        for rule in MAIN_RULES:
            for metric in ['credits','distinct_frozen_ids','excess_credits']:
                val={}
                for r in rows:
                    wid=r['work_id'];c=Fraction(r[env+'_'+rule]);d=Fraction(max(network[i,wid][env+'_'+rule] for i in incidence[wid]),r['degree'])
                    val[r['case_id']]=c if metric=='credits' else d if metric=='distinct_frozen_ids' else c-d
                values[env,rule,metric]=val
    for design in ['pilot_conditioned','full_40_expansion']:
        for env in ['none','crossref']:
            for rule in MAIN_RULES:
                for metric in ['credits','distinct_frozen_ids','excess_credits']:
                    for endpoint in ['level','change_from_baseline']:
                        v=values[env,rule,metric]
                        if endpoint!='level':v={k:x-values[env,'0000',metric][k] for k,x in v.items()}
                        estimates.append(dict(environment=env,estimator=design,rule=rule,rule_label=NAMES[rule],metric=metric,endpoint=endpoint,**estimate(groups,v,design)))
        for rule in MAIN_RULES+['combined_contrast']:
            for metric in ['credits','distinct_frozen_ids','excess_credits']:
                if rule=='combined_contrast':v={k:values['crossref','1111',metric][k]-values['crossref','0000',metric][k]-values['none','1111',metric][k]+values['none','0000',metric][k] for k in values['none','0000',metric]}
                else:v={k:x-values['none',rule,metric][k] for k,x in values['crossref',rule,metric].items()}
                sources.append(dict(estimator=design,rule=rule,metric=metric,**estimate(groups,v,design)))
        for env in ['none','crossref']:
            for rule in ['0010','1111']:
                for metric in ['credits','distinct_frozen_ids']:
                    known={};unknown={}
                    for r in rows:
                        k=r['case_id'];known[k]=(values[env,rule,metric][k]-values[env,'0000',metric][k])*(not r['redirect']);unknown[k]=Fraction(r['redirect'],1 if metric=='credits' else r['degree'])
                    k=estimate(groups,known,design)['estimate'];u=estimate(groups,unknown,design)['estimate']
                    identity.append(dict(environment=env,estimator=design,rule=rule,metric=metric,known_component=k,unknown_mass=u,arbitrary_contrast_lower=k-u,arbitrary_contrast_upper=k+u,structural_monotone_lower=k if rule=='0010' else ''))
    from exact import lower_count
    for env in ['none','crossref']:
        for rule in ['1000','0001']:
            relevant=list(groups.values()) if rule=='1000' else [groups['https://openalex.org/I119942576']]
            assert all(r[env+'_'+rule]==r[env+'_0000'] for r in rows)
            for design in ['pilot_conditioned','full_40_expansion']:
                upper=0
                for g in relevant:
                    N=int(g[0]['N']);M,n=(N-10,30) if design=='pilot_conditioned' else (N,40)
                    upper+=M-lower_count(M,n,n,20*len(relevant))
                zeros.append(dict(environment=env,rule=rule,estimator=design,affected_strata=len(relevant),one_sided_95_upper=upper,tail_alpha_denominator=20*len(relevant)))
    return groups,values,{'institutional_estimates':estimates,'source_environment_effects':sources,'redirect_sensitivity':identity,'zero_event_limits':zeros}

def documentary_bounds(rows,groups):
    docs={r['case_id']:r for r in load('evidence')['institutional']};out=[];N=sum(int(g[0]['N']) for g in groups.values())
    for env in ['none','crossref']:
        for sensitivity in ['main','I0122_role_unresolved','primary_files_only']:
            for expanded in [False,True]:
                known=unknown=E=I=0;byi=defaultdict(list)
                for r in rows:
                    d=r[env+'_1111']-r[env+'_0000'];label=docs.get(r['case_id'],{}).get('assessment','UNRESOLVED')
                    if sensitivity=='I0122_role_unresolved' and r['case_id']=='I0122':label='UNRESOLVED'
                    if sensitivity=='primary_files_only' and r['case_id'] in ['I0122','I1286']:label='UNRESOLVED'
                    w=int(r['N'])/40 if expanded else 1
                    if label=='UNRESOLVED':unknown+=w*abs(d);y=None
                    else:y=int(label=='ELIGIBLE');known+=w*d*(1-2*y);E+=w*y;I+=w*(1-y)
                    byi[r['institution_id']].append((r,y,w))
                B=sum((int(r['N'])/40 if expanded else 1)*r[env+'_0000'] for r in rows);C=sum((int(r['N'])/40 if expanded else 1)*r[env+'_1111'] for r in rows);total=N if expanded else len(rows)
                candidates=[E,total-I]+[x for x in [B,C] if E<=x<=total-I];loss=[abs(C-t)-abs(B-t) for t in candidates];lo=hi=0
                for g in byi.values():
                    e=sum(y==1 for r,y,w in g);u=sum(y is None for r,y,w in g);b=sum(r[env+'_0000'] for r,y,w in g);c=sum(r[env+'_1111'] for r,y,w in g);w=g[0][2];v=[w*(abs(c-t)-abs(b-t)) for t in range(e,e+u+1)];lo+=min(v);hi+=max(v)
                out.append(dict(environment=env,sensitivity=sensitivity,scale='full_40_weighted_sample' if expanded else 'sample',membership_loss_difference_lower=known-unknown,membership_loss_difference_upper=known+unknown,feasible_true_total_lower=E,feasible_true_total_upper=total-I,pooled_absolute_count_loss_difference_lower=min(loss),pooled_absolute_count_loss_difference_upper=max(loss),sum_institution_absolute_count_loss_difference_lower=lo,sum_institution_absolute_count_loss_difference_upper=hi))
    return out

def date_policies(rows,groups,crossref):
    works=load('institutional')['works'];values={};out=[];changes=[]
    for policy in ['archived_online_first','earliest_recorded_publication','print_first']:
        for rule in ['0000','0010','1111']:
            fn=prepare(rule);pred={}
            for r in rows:
                ev=copy.deepcopy(crossref[r['work_id']]);dates=ev.get('publication_dates',[])
                assert all(x['source_kind'] in ['crossref_published_online','crossref_published_print','crossref_issued'] and x.get('same_version') for x in dates)
                if dates and policy!='archived_online_first':
                    selected=min(dates,key=lambda x:resolver.parse_date(x['date'])) if policy=='earliest_recorded_publication' else min(dates,key=lambda x:['crossref_published_print','crossref_published_online','crossref_issued'].index(x['source_kind']))
                    ev['publication_dates']=[selected]
                yes=int(fn(works[r['work_id']],r['institution_id'],ev)['classification']=='SUPPORTED');pred[r['case_id']]=yes
                if policy=='archived_online_first':assert yes==r['crossref_'+rule]
                if yes!=r['crossref_'+rule]:changes.append(dict(case_id=r['case_id'],policy=policy,rule=rule,baseline_date_policy=r['crossref_'+rule],alternative=yes))
            values[policy,rule]=pred
    for policy in ['archived_online_first','earliest_recorded_publication','print_first']:
        for rule in ['0000','0010','1111']:
            for comparison in ['level','minus_archived_date_policy','minus_same_policy_baseline']:
                v={r['case_id']:Fraction(values[policy,rule][r['case_id']]-(0 if comparison=='level' else values['archived_online_first',rule][r['case_id']] if comparison=='minus_archived_date_policy' else values[policy,'0000'][r['case_id']])) for r in rows}
                for design in ['full_40_expansion','pilot_conditioned']:out.append(dict(date_policy=policy,rule=rule,comparison=comparison,estimator=design,sample_sum=float(sum(v.values())),**estimate(groups,v,design)))
    return out,changes

def bootstrap(groups,values):
    import numpy as np
    output=[];B=10000
    for design,environments in [('full_40_expansion',['none','crossref']),('pilot_conditioned',['crossref'])]:
        rng=np.random.default_rng(20261111)
        for env in environments:
            sim=np.zeros((B,3));center=np.zeros(3)
            for iid,g in sorted(groups.items()):
                N=int(g[0]['N']);pilot=np.zeros(3)
                def contrast(r):
                    return [float(values[env,'1111',m][r['case_id']]-values[env,'0000',m][r['case_id']]) for m in ['credits','distinct_frozen_ids','excess_credits']]
                if design=='pilot_conditioned':
                    pilot=np.array([contrast(r) for r in g if int(r['rank'])<=10]).sum(axis=0);g=[r for r in g if int(r['rank'])>10];M,n=N-10,30
                else:M,n=N,40
                arr=np.array([contrast(r) for r in g]);mu=arr.mean(axis=0);res=arr[rng.integers(0,n,size=(B,n))].mean(axis=1)
                sim+=pilot+M*(mu+math.sqrt(n/(n-1)*(1-n/M))*(res-mu));center+=pilot+M*mu
            for k,metric in enumerate(['credits','distinct_frozen_ids','excess_credits']):
                lo,hi=np.quantile(sim[:,k],[.025,.975]);output.append(dict(environment=env,estimator=design,metric=metric,replications=B,seed=20261111,estimate=float(center[k]),bootstrap_se=float(sim[:,k].std(ddof=1)),basic95_lower=float(2*center[k]-hi),basic95_upper=float(2*center[k]-lo)))
    return output

def run(output=None,core=False):
    rows,network,crossref,digest=evaluate();groups,values,tables=operational_estimates(rows,network);tables['documentary_loss_bounds']=documentary_bounds(rows,groups)
    data=load('institutional');evidence=load('evidence');seed=json.loads((DATA/'seed.json').read_text())['seed']
    assert {r['id'] for r in data['current_institutions']}==set(groups)
    assert len(data['current_institutions'])==50 and all(r['country_code']=='US' for r in data['current_institutions'])
    # The documentary queue is selected from pilot decisions before reading publications.
    queue=[]
    for group,limit in [('disagreement',20),('unchanged_accept',10),('unchanged_reject',10)]:
        eligible=[]
        for r in rows:
            if int(r['rank'])>10:continue
            b,c=r['none_0000'],r['none_1111'];category='disagreement' if b!=c else 'unchanged_accept' if b else 'unchanged_reject'
            if category==group:eligible.append((hashlib.sha256(f"DOCUMENTARY|{seed}|{r['institution_id']}|{r['work_id']}".encode()).hexdigest(),r['case_id']))
        queue.extend(cid for _,cid in sorted(eligible)[:limit])
    assert set(queue)=={r['case_id'] for r in evidence['institutional']}
    dois=[r['doi'].lower() for r in rows if r['doi']];assert len(dois)==len(set(dois))
    assert not set(dois)&set(data['previous_dois']) and not {r['canonical_id'] for r in rows}&set(data['previous_canonical_ids'])
    assert len({r['canonical_id'] for r in rows})==2000
    for p in load('provenance')['work_input_projection']:assert fingerprint(data['works'][p['requested_work_id']])==p['retained_object_sha256']
    diagnostics=[]
    for env in ['none','crossref']:
        changes=[r[env+'_1111']-r[env+'_0000'] for r in rows];rates=[]
        for iid,g in groups.items():
            dc=[r[env+'_1111']-r[env+'_0000'] for r in g];rates.append(sum(dc)/40)
        for rule in ['0010','1111']:
            zero=[g for g in groups.values() if all(r[env+'_'+rule]==r[env+'_0000'] for r in g if int(r['rank'])>10)]
            diagnostics.append(dict(environment=env,rule=rule,zero_reserve_strata=len(zero),zero_reserve_frame_pairs=sum(int(g[0]['N']) for g in zero),pilot_additions_in_zero_strata=sum(r[env+'_'+rule]-r[env+'_0000'] for g in zero for r in g if int(r['rank'])<=10)))
    primary=next(r for r in tables['institutional_estimates'] if r['environment']=='crossref' and r['estimator']=='pilot_conditioned' and r['rule']=='1111' and r['metric']=='credits' and r['endpoint']=='change_from_baseline')
    baseline=next(r['estimate'] for r in tables['institutional_estimates'] if r['environment']=='crossref' and r['estimator']=='pilot_conditioned' and r['rule']=='0000' and r['metric']=='credits' and r['endpoint']=='level')
    conference=next(r['estimate'] for r in tables['institutional_estimates'] if r['environment']=='crossref' and r['estimator']=='pilot_conditioned' and r['rule']=='0010' and r['metric']=='credits' and r['endpoint']=='change_from_baseline')
    summary=dict(sample_pairs=2000,universities=50,target_pairs=sum(int(g[0]['N']) for g in groups.values()),network_pair_evaluations=len(network),shared_sample_work_ids=sum(r['degree']>1 for r in rows),prediction_matrix_sha256=digest,redirects=sum(r['redirect'] for r in rows),stable_identifiers=sum(not r['redirect'] for r in rows),distinct_current_identifiers=len({r['canonical_id'] for r in rows}),doi_bearing_records=len(dois),exact_crossref_records=sum(r['crossref_exact'] for r in rows),crossref_author_affiliations=sum(r['crossref_affiliations']>0 for r in rows),current_focal_links=sum(r['current_focal'] for r in rows),pilot_stable_identifiers=sum(not r['redirect'] for r in rows if int(r['rank'])<=10),sample_acceptances={env+'_'+rule:sum(r[env+'_'+rule] for r in rows) for env in ['none','crossref'] for rule in MAIN_RULES},documentary_labels=dict(Counter(r['assessment'] for r in evidence['institutional'])),documentary_selection_verified=40,relative_credit_increase_percent=100*primary['estimate']/baseline,conference_share_percent=100*conference/primary['estimate'],baseline_acceptance_percent=100*baseline/1044517,corrected_acceptance_percent=100*(baseline+primary['estimate'])/1044517,zero_reserve_diagnostics=diagnostics,full_sample_changed_institutions=sum(any(r['crossref_1111']!=r['crossref_0000'] for r in g) for g in groups.values()),full_sample_median_rate=statistics.median(sum(r['crossref_1111']-r['crossref_0000'] for r in g)/40 for g in groups.values()),full_sample_max_rate=max(sum(r['crossref_1111']-r['crossref_0000'] for r in g)/40 for g in groups.values()))
    summary['source_changes']=[dict(rule=rule,changed=sum(r['crossref_'+rule]!=r['none_'+rule] for r in rows),added=sum(r['crossref_'+rule]>r['none_'+rule] for r in rows),removed=sum(r['crossref_'+rule]<r['none_'+rule] for r in rows)) for rule in ['0000','1111']]
    conflicts=[]
    for r in rows:
        if r['none_1111']!=1 or r['crossref_1111']!=0:continue
        dates=crossref[r['work_id']].get('publication_dates',[])
        if any(x['source_kind']=='crossref_published_online' and int(x['date'][:4])>2015 for x in dates) and any(x['source_kind']=='crossref_published_print' and 2005<=int(x['date'][:4])<=2015 for x in dates):conflicts.append(r['case_id'])
    summary['online_after_window_print_in_window']=conflicts
    summary['full_40_generic_hoeffding_halfwidth']=2*math.sqrt(math.log(40)*sum(int(g[0]['N'])**2/40 for g in groups.values())/2)
    if core:
        summary['frame_verification']=selection_check();tables['date_policies'],date_changes=date_policies(rows,groups,crossref);summary['date_policy_changed_cases']=date_changes;tables['bootstrap']=bootstrap(groups,values)
    if output:
        for name,rs in tables.items():write_csv(output/(name+'.csv'),rs)
        write_json(output/'institutional_details.json',summary)
    return {'tables':tables,'summary':summary,'rows':rows,'groups':groups,'values':values}
