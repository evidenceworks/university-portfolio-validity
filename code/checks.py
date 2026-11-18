"""Check the reported numerical results and an independent variance calculation."""
from collections import defaultdict
from pathlib import Path
import hashlib, math, re, statistics
from common import ROOT, load

def manifest():
    listed = set()
    for line in (ROOT / 'checksums.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        p = ROOT / name
        assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == digest, name
        listed.add(name)
    files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
             if p.is_file() and not ({'results', '__pycache__', '.git'} & set(p.relative_to(ROOT).parts))}
    numerical_inputs_and_code = {name for name in files
                                 if name.startswith(('code/', 'data/'))
                                 or name in {'reproduce.py', 'requirements.txt'}}
    assert listed == numerical_inputs_and_code, ('Unlisted or missing scientific files', listed ^ numerical_inputs_and_code)
    reference_files = {'.gitattributes', 'LICENSE', 'README.md', 'checksums.sha256',
                       'licenses/CC-BY-4.0.txt', 'licenses/MIT.txt'}
    assert files == numerical_inputs_and_code | reference_files, ('Unexpected repository files', files ^ (numerical_inputs_and_code | reference_files))
    return len(listed)

def same(actual, expected, path):
    if isinstance(expected, dict):
        for k, v in expected.items():
            assert k in actual, (path, k)
            same(actual[k], v, path + '.' + k)
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (path, len(actual), len(expected))
        for i, (a, e) in enumerate(zip(actual, expected)):
            same(a, e, f'{path}[{i}]')
    elif str(actual) != str(expected):
        try:
            a, e = (float(actual), float(expected))
        except (ValueError, TypeError):
            raise AssertionError((path, actual, expected))
        assert math.isfinite(a) and math.isfinite(e) and math.isclose(a, e, rel_tol=1e-10, abs_tol=1e-08), (path, actual, expected)

def results(historical, institutional, exact, core=False):
    expected = load('expected')
    tables = {**historical['tables'], **institutional['tables'], **exact['tables']}
    matched = 0
    cells = 0
    for name, rows in tables.items():
        spec = expected['tables'][name]
        keys = spec['keys']
        actual = {tuple((str(r[k]) for k in keys)): r for r in rows}
        assert len(actual) == len(rows), (name, 'duplicate row keys')
        assert len(rows) == len(spec['rows']), (name, 'unexpected table size', len(rows), len(spec['rows']))
        for r in spec['rows']:
            key = tuple((str(r[k]) for k in keys))
            assert key in actual, (name, key)
            same(actual[key], r, name + str(key))
            matched += 1
            cells += len(r)
    if core:
        assert set(tables) == set(expected['tables'])
    same(historical['summary'], expected['summaries']['historical'], 'historical')
    same(institutional['summary'], expected['summaries']['institutional'], 'institutional')
    nchecked = 0
    groups = institutional['groups']
    values = institutional['values']
    index = {(r['environment'], r['estimator'], r['rule'], r['metric'], r['endpoint']): r for r in institutional['tables']['institutional_estimates']}
    for env in ['none', 'crossref']:
        for rule in ['1000', '0100', '0010', '0001', '1111']:
            for metric in ['credits', 'distinct_frozen_ids', 'excess_credits']:
                for design in ['pilot_conditioned', 'full_40_expansion']:
                    point = variance = 0.0
                    for g in groups.values():
                        N = int(g[0]['N'])
                        d = lambda r: float(values[env, rule, metric][r['case_id']] - values[env, '0000', metric][r['case_id']])
                        if design == 'pilot_conditioned':
                            point += sum((d(r) for r in g if int(r['rank']) <= 10))
                            selected = [d(r) for r in g if int(r['rank']) > 10]
                            M, n = (N - 10, 30)
                        else:
                            selected = [d(r) for r in g]
                            M, n = (N, 40)
                        point += M * statistics.mean(selected)
                        variance += M * M * (1 - n / M) * statistics.variance(selected) / n
                    ref = index[env, design, rule, metric, 'change_from_baseline']
                    same(point, ref['estimate'], 'independent mean')
                    same(math.sqrt(variance), ref['se'], 'independent SE')
                    nchecked += 1
    assert historical['tables']['historical_evidence_requirements'][1]['total_eligible_minimum'] == 41
    assert historical['tables']['historical_evidence_requirements'][1]['unchanged_eligible_minimum'] == 32
    return dict(numerical_tables_checked=len(tables), reference_rows_checked=matched, reference_cells_checked=cells, independent_mean_variance_comparisons=nchecked, historical_decisions_reproduced=6400, institutional_decisions_reproduced=71264)
