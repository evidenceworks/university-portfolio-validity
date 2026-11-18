"""Historical rule comparisons and exact requirements for grouped-count validation."""
from collections import Counter,defaultdict
from fractions import Fraction
import itertools,math
from common import cases,load,prepare,CONFIGS,MAIN_RULES,NAMES,fingerprint,write_csv,write_json
OLD='0000'
NEW='1111'

def metric(cases, prediction, truth):
    counts = Counter()
    by_institution = defaultdict(lambda: [0, 0])
    for c in cases:
        cid = c['case_id']
        a, y = prediction[cid], truth[cid]
        assert a in (0, 1) and y in (0, 1)
        counts[('TP' if y else 'FP') if a else ('FN' if y else 'TN')] += 1
        by_institution[c['institution_id']][0] += a
        by_institution[c['institution_id']][1] += y
    counts.update({'accepted': sum(prediction.values()), 'eligible': sum(truth.values())})
    counts['membership_error'] = counts['FP'] + counts['FN']
    counts['pooled_error'] = abs(counts['accepted'] - counts['eligible'])
    counts['university_error'] = sum(abs(a-y) for a, y in by_institution.values())
    return {k: counts[k] for k in ('TP', 'FP', 'FN', 'TN', 'accepted', 'eligible', 'membership_error', 'pooled_error', 'university_error')}

def exact_frontier(metrics):
    policies = defaultdict(list)
    for row in metrics:
        policies[(row['FP'], row['FN'])].append(row['policy'])
    knots = {Fraction(0)}
    for (fp, fn), (fp2, fn2) in itertools.combinations(policies, 2):
        if fp != fp2:
            x = Fraction(fn2-fn, fp-fp2)
            if x >= 0:
                knots.add(x)
    knots = sorted(knots)
    result = []
    for lower, upper in zip(knots, knots[1:] + [None]):
        x = (lower + upper) / 2 if upper is not None else lower + 1
        best = min(fp*x + fn for fp, fn in policies)
        winner = [(fp, fn) for fp, fn in policies if fp*x + fn == best]
        names = ';'.join(sorted(name for key in winner for name in policies[key]))
        row = dict(lambda_lower=str(lower), lambda_upper=str(upper) if upper is not None else 'infinity', policies=names, FP=winner[0][0], FN=winner[0][1])
        if result and names == result[-1]['policies']:
            result[-1]['lambda_upper'] = row['lambda_upper']
        else:
            result.append(row)
    return result

def pair_bounds(cases, a, b, labels):
    # Difference L(a) - L(b). Each endpoint is slope * lambda + intercept.
    lower_slope = lower_intercept = upper_slope = upper_intercept = 0
    for c in cases:
        cid = c['case_id']
        d = a[cid] - b[cid]
        if not d:
            continue
        y = labels[cid]
        if y == 1:
            lower_intercept -= d
            upper_intercept -= d
        elif y == 0:
            lower_slope += d
            upper_slope += d
        elif d == 1:
            lower_intercept -= 1
            upper_slope += 1
        else:
            lower_slope -= 1
            upper_intercept += 1
    return dict(lower_slope=lower_slope, lower_intercept=lower_intercept, upper_slope=upper_slope, upper_intercept=upper_intercept, lower_at_lambda_1=lower_slope+lower_intercept, upper_at_lambda_1=upper_slope+upper_intercept)

def count_analysis(cases, groups, old, new, labels, mode, changed):
    witnesses, options, low_truth, high_truth = [], [], {}, {}
    low_sum = high_sum = tested_assignments = 0
    unknown_relevant = 0
    only_changed_upper = 0
    for iid, group in sorted(groups.items()):
        known = sorted(c['case_id'] for c in group if labels[c['case_id']] == 1)
        excluded = sorted(c['case_id'] for c in group if labels[c['case_id']] == 0)
        unknown = sorted(c['case_id'] for c in group if labels[c['case_id']] is None)
        k, u = len(known), len(unknown)
        n0 = sum(old[c['case_id']] for c in group)
        n1 = sum(new[c['case_id']] for c in group)
        delta = n1-n0
        assert delta >= 0 and len(group) == 8
        f = lambda t: abs(n1-t) - abs(n0-t)
        # Independently exhaust every permitted binary assignment, not just totals.
        assignments = []
        for bits in itertools.product((0, 1), repeat=u):
            t = k + sum(bits)
            assignments.append((f(t), bits))
        tested_assignments += len(assignments)
        lo = min(v for v, bits in assignments)
        hi = max(v for v, bits in assignments)
        assert (lo, hi) == (f(k+u), f(k))
        # Canonical witnesses: every unknown eligible for minimum; ineligible for maximum.
        for c in group:
            cid = c['case_id']
            low_truth[cid] = int(labels[cid] != 0)
            high_truth[cid] = int(labels[cid] == 1)
        low_sum += lo
        high_sum += hi
        changed_unknown = [cid for cid in unknown if cid in changed]
        only_changed_upper += f(k+len(changed_unknown))
        witnesses.append(dict(mode=mode, institution_id=iid, institution=group[0]['institution_name'], historical_count=n0, corrected_count=n1, fixed_eligible=k, fixed_ineligible=len(excluded), uncertain=u, lower=lo, upper=hi, lower_eligible_case_ids=';'.join(known+unknown), upper_eligible_case_ids=';'.join(known), uncertain_case_ids=';'.join(unknown), uncertain_changed_case_ids=';'.join(changed_unknown), upper_if_all_uncertain_changed_are_eligible=f(k+len(changed_unknown))))
        if delta:
            unknown_relevant += u
            # All labels at this institution have equal information value for this count objective.
            local = [(r, hi-f(k+r)) for r in range(u+1)]
            options.append((group, unknown, local, hi, k, n0, n1))
    assert metric(cases, new, low_truth)['university_error'] - metric(cases, old, low_truth)['university_error'] == low_sum
    assert metric(cases, new, high_truth)['university_error'] - metric(cases, old, high_truth)['university_error'] == high_sum
    # Exact multiple-choice knapsack over 24 affected institutions.
    dp = {0: (0, [])}
    for group, unknown, local, hi, k, n0, n1 in options:
        nxt = {}
        for previous_cost, (previous_gain, previous_witness) in dp.items():
            for cost, gain in local:
                new_cost, new_gain = previous_cost+cost, previous_gain+gain
                candidate = previous_witness + [(group[0]['institution_id'], unknown[:cost])]
                if new_cost not in nxt or new_gain > nxt[new_cost][0]:
                    nxt[new_cost] = (new_gain, candidate)
        dp = nxt
    info_curve = [dict(mode=mode, additional_eligible_confirmations=cost, maximum_upper_endpoint_reduction=dp[cost][0], best_possible_upper_endpoint=high_sum-dp[cost][0]) for cost in sorted(dp)]
    feasible = [cost for cost, (gain, witness) in dp.items() if gain > high_sum]
    minimum = min(feasible) if feasible else None
    chosen = [] if minimum is None else [cid for iid, ids in dp[minimum][1] for cid in ids]
    chosen_set = set(chosen)
    if minimum is not None:
        assert len(chosen_set) == minimum
        updated = dict(labels)
        for cid in chosen:
            assert updated[cid] is None
            updated[cid] = 1
        check_upper = 0
        for iid, group in groups.items():
            n0 = sum(old[c['case_id']] for c in group)
            n1 = sum(new[c['case_id']] for c in group)
            k = sum(updated[c['case_id']] == 1 for c in group)
            check_upper += abs(n1-k) - abs(n0-k)
        assert check_upper < 0
        assert all(high_sum-dp[cost][0] >= 0 for cost in range(minimum))
    priorities = []
    for group, unknown, local, hi, k, n0, n1 in options:
        first_gain = next((cost for cost, gain in local if gain > 0), None)
        for cid in unknown:
            c = next(c for c in group if c['case_id'] == cid)
            priorities.append(dict(mode=mode, case_id=cid, institution=c['institution_name'], work_id=c['work_id'], historical_grade=c['reference_grade'], historical_decision=c['decision'], changed_case=int(cid in changed), in_minimum_positive_information_witness=int(cid in chosen_set), institution_initial_upper=hi, institution_minimum_confirmations_for_any_reduction=first_gain if first_gain is not None else 'unattainable', source_1=c['source_1'], source_2=c['source_2']))
    summary = dict(university_error_change_lower=low_sum, university_error_change_upper=high_sum, exhaustive_local_assignments_tested=tested_assignments, relevant_uncertain_labels=unknown_relevant, upper_if_all_uncertain_changed_cases_eligible=only_changed_upper, minimum_additional_eligible_confirmations_for_negative_upper=minimum, minimum_information_witness=chosen, minimum_information_witness_changed_count=sum(cid in changed for cid in chosen), minimum_information_witness_unchanged_count=sum(cid not in changed for cid in chosen), lower_witness_metrics={OLD:metric(cases, old, low_truth), NEW:metric(cases, new, low_truth)}, upper_witness_metrics={OLD:metric(cases, old, high_truth), NEW:metric(cases, new, high_truth)})
    return summary, witnesses, info_curve, priorities, low_truth, high_truth

def reference_sets(records,evidence):
    ids=[c['case_id'] for c in records]
    frozen={c['case_id']:int(c['reference_grade']!='INVALID') for c in records}
    grade_b={c['case_id']:None if c['reference_grade']=='VALID_B' else frozen[c['case_id']] for c in records}
    relaxed=dict(grade_b);relaxed['R1D036']=None
    historical_doc=dict(relaxed);documentary={cid:None for cid in ids}
    for r in evidence['historical_additions']+evidence['historical_unchanged']:
        if r['documentary_eligibility']!='UNRESOLVED':
            historical_doc[r['case_id']]=documentary[r['case_id']]=int(r['documentary_eligibility']=='ELIGIBLE')
    unresolved=dict(documentary);unresolved['R1D038']=None
    return {'Historical reference':frozen,'Grade B uncertain':grade_b,'Grade B and R1D036 uncertain':relaxed,'Historical + documentary':historical_doc,'Documentary only':documentary,'R1D038 unresolved':unresolved}

def information(groups,old,new,labels,summary,witnesses):
    """Find adverse, unchanged-decision and jointly attaining evidence minima."""
    negative={0:0};unchanged={0:(0,[])};curved=0;nonaffine=[];all_additions=[]
    for row in witnesses:
        h,c,k,u=[int(row[n]) for n in ['historical_count','corrected_count','fixed_eligible','uncertain']]
        f=lambda t:abs(c-t)-abs(h-t)
        unknown=[x for x in row['uncertain_case_ids'].split(';') if x]
        additions=[x for x in row['uncertain_changed_case_ids'].split(';') if x]
        other=[x for x in unknown if x not in additions];all_additions+=additions
        local=[f(k+u-r) for r in range(u+1)] if h!=c else [0]
        nxt={}
        for cost,score in negative.items():
            for r,value in enumerate(local):nxt[cost+r]=max(nxt.get(cost+r,-10000),score+value)
        negative=nxt
        nxt={}
        for score,(cost,ids) in unchanged.items():
            for r in range(len(other)+1):
                v=score+f(k+len(additions)+r);candidate=(cost+r,ids+other[:r])
                if v not in nxt or candidate[0]<nxt[v][0]:nxt[v]=candidate
        unchanged=nxt
        for t in range(k,k+u-1):
            d2=f(t+2)-2*f(t+1)+f(t)
            if d2:
                curved+=1;nonaffine.append(dict(institution=row['institution'],h=h,c=c,k=k,u=u,other_eligible=t,values=[f(t),f(t+1),f(t+1),f(t+2)],mixed_difference=d2));break
    adverse=min((n for n,v in negative.items() if v>0),default=None)
    upper,(unchanged_min,ids)=min(((score,v) for score,v in unchanged.items() if score<0),key=lambda x:x[1][0])
    # A separate budget-indexed recurrence checks the score-indexed minimum.
    dp={0:0};enumerated=0
    for group in groups.values():
        ids0=[c['case_id'] for c in group];h=sum(old[i] for i in ids0);c=sum(new[i] for i in ids0);k=sum(labels[i]==1 for i in ids0)
        added=[i for i in ids0 if labels[i] is None and new[i]!=old[i]];other=[i for i in ids0 if labels[i] is None and new[i]==old[i]]
        local={}
        for bits in itertools.product((0,1),repeat=len(other)):
            q=sum(bits);t=k+len(added)+q;v=abs(c-t)-abs(h-t);local[q]=min(local.get(q,10000),v);enumerated+=1
        nxt={}
        for b,v in dp.items():
            for q,value in local.items():nxt[b+q]=min(nxt.get(b+q,10000),v+value)
        dp=nxt
    assert min(b for b,v in dp.items() if v<0)==unchanged_min and dp[unchanged_min]==upper
    total_min=summary['minimum_additional_eligible_confirmations_for_negative_upper']
    # Joint allocation attains the total and unchanged-decision minima together.
    joint={(0,0):(0,[])}
    for group in groups.values():
        ids0=[c['case_id'] for c in group];h=sum(old[i] for i in ids0);c=sum(new[i] for i in ids0);k=sum(labels[i]==1 for i in ids0)
        added=[i for i in ids0 if labels[i] is None and new[i]!=old[i]];other=[i for i in ids0 if labels[i] is None and new[i]==old[i]]
        local=[(a,b,abs(c-k-a-b)-abs(h-k-a-b),added[:a]+other[:b]) for a in range(len(added)+1) for b in range(len(other)+1)] if h!=c else [(0,0,0,[])]
        nxt={}
        for (t,b),(v,chosen) in joint.items():
            for a,q,value,extra in local:
                key=(t+a+q,b+q)
                if key[0]>total_min or key[1]>unchanged_min:continue
                if key not in nxt or v+value<nxt[key][0]:nxt[key]=(v+value,chosen+extra)
        joint=nxt
    score,chosen=joint[total_min,unchanged_min];assert score<0 and len(set(chosen))==total_min
    updated=dict(labels)
    for cid in chosen:assert updated[cid] is None;updated[cid]=1
    direct=sum(abs(sum(new[c['case_id']] for c in g)-sum(updated[c['case_id']]==1 for c in g))-abs(sum(old[c['case_id']] for c in g)-sum(updated[c['case_id']]==1 for c in g)) for g in groups.values())
    assert direct==score
    return dict(total_eligible_minimum=total_min,unchanged_eligible_minimum=unchanged_min,changed_eligible_in_joint_minimum=total_min-unchanged_min,joint_upper=score,upper_one_below_unchanged_minimum=dp[unchanged_min-1],adverse_ineligible_minimum=adverse,nonaffine_institutions=curved,independent_assignments_enumerated=enumerated,joint_witness=chosen,nonaffine_witnesses=nonaffine)

def run(output=None):
    records=cases();hdata=load('historical');evidence=load('evidence');groups=defaultdict(list)
    for c in records:groups[c['institution_id']].append(c)
    predictions={};statuses=[]
    for config in CONFIGS:
        fn=prepare(config,historical=True);prediction={}
        for item in hdata['inputs']:
            answer=fn(item['work'],item['focal'],item['evidence']);prediction[item['case_id']]=int(answer['classification']=='SUPPORTED')
            statuses.append([config,item['case_id'],answer['classification']])
        predictions[config]=prediction
    predictions['accept_all_candidates']={c['case_id']:1 for c in records};predictions['reject_all_candidates']={c['case_id']:0 for c in records}
    old,new=predictions[OLD],predictions[NEW]
    assert all(old[c['case_id']]==int(c['decision']=='SUPPORTED') for c in records)
    changed={cid for cid in old if new[cid]!=old[cid]};assert len(changed)==39 and all(new[i]>old[i] for i in changed)
    modes=reference_sets(records,evidence);truth=modes['Historical reference'];factorial=[]
    for policy,pred in predictions.items():factorial.append(dict(policy=policy,**metric(records,pred,truth)))
    frontier=exact_frontier(factorial);bounds=[];requirements=[];curves=[];witness_data={};exact_checks=0
    for mode,labels in modes.items():
        s,w,curve,_,_,_=count_analysis(records,groups,old,new,labels,mode,changed);exact_checks+=s['exhaustive_local_assignments_tested']
        e=sum(v==1 for v in labels.values());i=sum(v==0 for v in labels.values());u=400-e-i
        pool=[abs(sum(new.values())-t)-abs(sum(old.values())-t) for t in range(e,e+u+1)]
        pair=pair_bounds(records,new,old,labels)
        bounds.append(dict(evidence=mode,fixed_eligible=e,fixed_ineligible=i,uncertain=u,**pair,university_lower=s['university_error_change_lower'],university_upper=s['university_error_change_upper'],pooled_lower=min(pool),pooled_upper=max(pool)))
        if mode in ['Historical + documentary','Documentary only','R1D038 unresolved']:
            req=information(groups,old,new,labels,s,w);witness_data[mode]=req
            rejected=[cid for cid in old if not new[cid]];er=sum(labels[cid]==1 for cid in rejected);ir=sum(labels[cid]==0 for cid in rejected)
            requirements.append(dict(evidence=mode,total_eligible_minimum=req['total_eligible_minimum'],unchanged_eligible_minimum=req['unchanged_eligible_minimum'],changed_in_joint_minimum=req['changed_eligible_in_joint_minimum'],joint_upper=req['joint_upper'],upper_from_additions_only=s['upper_if_all_uncertain_changed_cases_eligible'],upper_one_below_unchanged_minimum=req['upper_one_below_unchanged_minimum'],adverse_ineligible_minimum=req['adverse_ineligible_minimum'],nonaffine_institutions=req['nonaffine_institutions'],additional_eligible_for_pooled_improvement=max(0,326-e) if e+u>=326 else '',additional_ineligible_for_pooled_deterioration=max(0,75-i) if i+u>=75 else '',rejected_fixed_eligible=er,rejected_fixed_ineligible=ir,rejected_uncertain=55-er-ir,correction_minus_accept_all_lower=2*er-55,correction_minus_accept_all_upper=55-2*ir,additional_ineligible_for_correction_beating_accept_all=max(0,28-ir) if 55-er>=28 else '',additional_eligible_for_accept_all_beating_correction=max(0,28-er) if 55-ir>=28 else ''))
            curves.extend(curve)
    weights={r['institution_id']:Fraction(int(r['candidate_count']),8) for r in hdata['institutions']};weighted=[]
    for policy in [OLD,NEW]:
        fp=fn=accepted=eligible=Fraction()
        for c in records:
            w=weights[c['institution_id']];y=truth[c['case_id']];a=predictions[policy][c['case_id']]
            accepted+=w*a;eligible+=w*y;fp+=w*int(a and not y);fn+=w*int(y and not a)
        weighted.append(dict(policy=policy,accepted=float(accepted),eligible=float(eligible),FP=float(fp),FN=float(fn),retention=float((eligible-fn)/eligible)))
    weighted_bounds=[]
    for mode,labels in modes.items():
        if mode=='R1D038 unresolved':continue
        for lam in [0,1,2,5,12]:
            lo=hi=Fraction()
            for c in records:
                cid=c['case_id'];d=new[cid]-old[cid];w=weights[c['institution_id']];ys=[0,1] if labels[cid] is None else [labels[cid]];v=[w*d*(lam-(lam+1)*y) for y in ys];lo+=min(v);hi+=max(v)
            weighted_bounds.append(dict(evidence=mode,relative_false_inclusion_cost=lam,lower=float(lo),upper=float(hi)))
    decomposition=[];institution_changes=[]
    for policy in [OLD,NEW]:
        signed=[];within=0
        for iid,g in groups.items():
            fp=sum(predictions[policy][c['case_id']] and not truth[c['case_id']] for c in g);fn=sum(not predictions[policy][c['case_id']] and truth[c['case_id']] for c in g);signed.append(fp-fn);within+=min(fp,fn)
        between=min(sum(max(x,0) for x in signed),sum(max(-x,0) for x in signed));m=sum(r['membership_error'] for r in factorial if r['policy']==policy)
        decomposition.append(dict(policy=policy,membership=m,university=sum(abs(x) for x in signed),pooled=abs(sum(signed)),within_cancellation_pairs=within,between_cancellation_pairs=between))
        assert m==abs(sum(signed))+2*within+2*between
    for iid,g in groups.items():
        t=sum(truth[c['case_id']] for c in g);a=sum(old[c['case_id']] for c in g);b=sum(new[c['case_id']] for c in g);institution_changes.append(abs(b-t)-abs(a-t))
    exclusion={policy:metric([c for c in records if c['case_id']!='R1D036'],{k:v for k,v in predictions[policy].items() if k!='R1D036'},{k:v for k,v in truth.items() if k!='R1D036'}) for policy in [OLD,NEW]}
    # Reconcile the archived passes against the unchanged observations.
    byid={c['case_id']:c for c in records};passes=evidence['classification_passes']
    for r in passes:
        result=r['pass_1'] if r['pass_1']==r['pass_2'] else r['resolution_pass']
        assert result==byid[r['case_id']]['reference_grade']==r['current_label']
    # Membership robustness releases each favorable finding separately.
    documentary=modes['Documentary only'];positive=[cid for cid in changed if documentary[cid]==1];fragility=[]
    for cid in sorted(positive):
        released=dict(documentary);released[cid]=None;reversed_label=dict(documentary);reversed_label[cid]=0
        fragility.append(dict(case_id=cid,released=pair_bounds(records,new,old,released),reversed=pair_bounds(records,new,old,reversed_label)))
    source={r['unitid']:r for r in hdata['herd']};inputs={r['case_id']:r for r in hdata['inputs']};herd_counts=[]
    for iid,g in groups.items():
        uid=str(inputs[g[0]['case_id']]['unitid'])
        if uid in source:herd_counts.append(sum(inputs[c['case_id']]['work']['publication_year']==2015 for c in g))
    summary=dict(cases=400,universities=len(groups),grades=dict(Counter(c['reference_grade'] for c in records)),classification_pass_exact_agreement=sum(r['pass_1']==r['pass_2'] for r in passes),classification_resolutions=sum(r['pass_1']!=r['pass_2'] for r in passes),classification_binary_agreement=sum((r['pass_1'] in ['VALID_A','VALID_B'])==(r['pass_2'] in ['VALID_A','VALID_B']) for r in passes),classification_three_state_agreement=sum((1 if r['pass_1'] in ['VALID_A','VALID_B'] else 0 if r['pass_1']=='INVALID' else None)==(1 if r['pass_2'] in ['VALID_A','VALID_B'] else 0 if r['pass_2']=='INVALID' else None) for r in passes),shared_source_cases=sum(r['any_exact_url_overlap']=='True' for r in evidence['classification_source_overlap']),historical_status_sha256=fingerprint(sorted(statuses)),changed=39,documentary_addition_labels=dict(Counter(r['documentary_eligibility'] for r in evidence['historical_additions'])),decomposition=decomposition,institution_counts_improved=sum(v<0 for v in institution_changes),institution_counts_worsened=sum(v>0 for v in institution_changes),institution_counts_unchanged=sum(v==0 for v in institution_changes),excluded_R1D036=exclusion,local_assignments_checked=exact_checks,herd_source_rows=len(hdata['herd']),herd_rd_thousand_usd=sum(int(r['rd_total_thousand_usd']) for r in hdata['herd']),herd_2015_audit_pairs=sum(herd_counts),herd_institutions_with_2015=sum(n>0 for n in herd_counts),herd_institutions_with_two_2015=sum(n>=2 for n in herd_counts),leiden_source_rows=len(hdata['leiden']),leiden_matches=sum(bool(r['leiden_id']) for r in hdata['leiden_crosswalk']),source_fragility=fragility,attaining_assignments=witness_data)
    tables={'historical_factorial':factorial,'historical_accuracy_bounds':bounds,'historical_evidence_requirements':requirements,'historical_loss_frontier':frontier,'historical_weighted_counts':weighted,'historical_weighted_bounds':weighted_bounds,'historical_evidence_frontier':curves}
    if output:
        for name,rs in tables.items():write_csv(output/(name+'.csv'),rs)
        write_json(output/'historical_details.json',summary)
    return {'tables':tables,'summary':summary,'predictions':predictions}
