"""Exact finite-population bounds for fixed operational addition counts.

Coverage is within each stated endpoint family under the stratified permutation
model. Pilot-conditioned inference fixes all pilot observations. Record screens
remain fixed on the whole frame; a failed screen contributes zero.
"""
from collections import defaultdict
from functools import lru_cache
from fractions import Fraction
import itertools,math
from common import CONFIGS,write_csv,write_json

@lru_cache(maxsize=None)
def tail_numerator(N, n, K, x):
    """Numerator of P[X >= x], denominator comb(N,n)."""
    if x<=0:return math.comb(N,n)
    lower=max(x,0,n-(N-K)); upper=min(n,K)
    return sum(math.comb(K,k)*math.comb(N-K,n-k) for k in range(lower,upper+1))

@lru_cache(maxsize=None)
def lower_count(N, n, x, alpha_denominator):
    """Invert the exact upper tail at alpha=1/alpha_denominator."""
    if x==0:return 0
    den=math.comb(N,n)
    lo,hi=0,N
    while lo<hi:
        mid=(lo+hi)//2
        if tail_numerator(N,n,mid,x)*alpha_denominator>=den:hi=mid
        else:lo=mid+1
    L=lo
    assert tail_numerator(N,n,L,x)*alpha_denominator>=den
    assert L==0 or tail_numerator(N,n,L-1,x)*alpha_denominator<den
    return L

def self_check():
    """Exhaustive achieved-coverage check on small finite populations."""
    tests=0; worst=Fraction()
    for N in range(2,21):
        for n in range(1,N+1):
            den=math.comb(N,n)
            for a in (20,1000,16000,32000):
                bounds={x:lower_count(N,n,x,a) for x in range(n+1)}
                for K in range(N+1):
                    failure=sum(math.comb(K,x)*math.comb(N-K,n-x)
                        for x in range(max(0,n-(N-K)),min(n,K)+1) if bounds[x]>K)
                    assert failure*a<=den
                    worst=max(worst,Fraction(failure*a,den)); tests+=1
    two_sided_tests=0
    for N in range(2,21):
        for n in range(1,N+1):
            den=math.comb(N,n);a=32000
            bounds={x:(lower_count(N,n,x,a),N-lower_count(N,n,n-x,a)) for x in range(n+1)}
            for K in range(N+1):
                failure=sum(math.comb(K,x)*math.comb(N-K,n-x) for x in range(max(0,n-(N-K)),min(n,K)+1) if bounds[x][0]>K or bounds[x][1]<K)
                assert failure*a<=2*den
                two_sided_tests+=1
    return {'finite_population_one_sided_coverage_checks':tests,'maximum_failure_to_nominal_ratio':float(worst),'two_sided_coverage_checks':two_sided_tests,'two_sided_tail_alpha_denominator':32000}

def run(rows,output=None,core=False):
    groups=defaultdict(list)
    for r in rows:groups[r['institution_id']].append(r)
    assert len(rows)==2000 and len(groups)==50
    singles=['1000','0100','0010','0001']
    families=[('conference_single_endpoint',1,['0010'],['crossref'],['all']),('conference_screened_single_endpoint',1,['0010'],['crossref'],['stable_exact_doi']),('conference_four_endpoints',4,['0010'],['none','crossref'],['all','stable_exact_doi']),('four_corrections_sixteen_endpoints',16,singles,['none','crossref'],['all','stable_exact_doi']),('all_configurations_sixtyfour_endpoints',64,CONFIGS,['none','crossref'],['all','stable_exact_doi'])]
    result=[]
    for family,m,rules,environments,screens in families:
        assert len(rules)*len(environments)*len(screens)==m
        for design in ['full_40_expansion','pilot_conditioned']:
            for rule,env,screen in itertools.product(rules,environments,screens):
                total=pilot=reserve=0;point=Fraction()
                for g in groups.values():
                    N=int(g[0]['N'])
                    def event(r):return int(r[env+'_'+rule]==1 and r[env+'_0000']==0 and (screen=='all' or (not r['redirect'] and r['crossref_exact'])))
                    xp=sum(event(r) for r in g if int(r['rank'])<=10);xr=sum(event(r) for r in g if int(r['rank'])>10)
                    M,n,x,known=(N,40,xp+xr,0) if design=='full_40_expansion' else (N-10,30,xr,xp)
                    total+=known+lower_count(M,n,x,20*50*m);point+=known+Fraction(M*x,n);pilot+=xp;reserve+=xr
                result.append(dict(family=family,family_endpoints=m,estimator=design,rule=rule,environment=env,screen=screen,tails=1,tail_alpha_denominator=20*50*m,pilot_events=pilot,reserve_events=reserve,point_estimate=float(point),lower_95_simultaneous=total,upper_95_simultaneous='',interpretation='net conference change' if rule=='0010' else 'positive additions'))
    zero_upper={}
    for rule,env,screen in itertools.product(singles,['none','crossref'],['all','stable_exact_doi']):
        lower=upper=pilot=reserve=0;point=Fraction();zero_count=zero_frame=zero_pilot=zero_sum=0
        for g in groups.values():
            N=int(g[0]['N']);M=N-10
            def event(r):return int(r[env+'_'+rule]==1 and r[env+'_0000']==0 and (screen=='all' or (not r['redirect'] and r['crossref_exact'])))
            xp=sum(event(r) for r in g if int(r['rank'])<=10);xr=sum(event(r) for r in g if int(r['rank'])>10)
            lo=xp+lower_count(M,30,xr,32000);hi=xp+M-lower_count(M,30,30-xr,32000)
            assert lo<=hi
            lower+=lo;upper+=hi;pilot+=xp;reserve+=xr;point+=xp+Fraction(M*xr,30)
            if xr==0:zero_count+=1;zero_frame+=N;zero_pilot+=xp;zero_sum+=hi
        result.append(dict(family='four_corrections_sixteen_endpoints',family_endpoints=16,estimator='pilot_conditioned',rule=rule,environment=env,screen=screen,tails=2,tail_alpha_denominator=32000,pilot_events=pilot,reserve_events=reserve,point_estimate=float(point),lower_95_simultaneous=lower,upper_95_simultaneous=upper,interpretation='net conference change' if rule=='0010' else 'positive additions'))
        if rule=='0010':zero_upper[env+'_'+screen]=dict(strata=zero_count,frame_pairs=zero_frame,pilot_additions=zero_pilot,upper_contribution=zero_sum)
    tested=0
    for r in rows:
        for env in ['none','crossref']:
            for config in CONFIGS:
                if config[2]=='0':assert r[env+'_'+config[:2]+'1'+config[3:]]>=r[env+'_'+config];tested+=1
    report={'conference_background_comparisons':tested,'zero_event_conference_strata':zero_upper,'arithmetic':'Integer hypergeometric tails with both inversion boundary checks.','coverage':'Separate coverage for each family and sampling treatment. The screened single-endpoint family is marginal, separate from the unrestricted single-endpoint family.','two_sided_rule':'Known pilot additions plus remainder size minus the lower bound on failures.'}
    if core:report['exhaustive_small_population_checks']=self_check()
    if output:write_csv(output/'finite_population_bounds.csv',result);write_json(output/'exact_checks.json',report)
    return {'tables':{'finite_population_bounds':result},'summary':report}
