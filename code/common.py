"""Read the frozen inputs and apply the four fixed rule changes."""
from pathlib import Path
from functools import lru_cache
import copy, csv, gzip, hashlib, json
import resolver
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CONFIGS = [f'{s}{a}{c}{p}' for s in (0, 1) for a in (0, 1) for c in (0, 1) for p in (0, 1)]
MAIN_RULES = ['0000', '1000', '0100', '0010', '0001', '1111']
NAMES = {'0000': 'Baseline', '1000': 'S Schema', '0100': 'A Apostrophe', '0010': 'C Conference', '0001': 'P Pacific', '1111': 'All four'}

@lru_cache(maxsize=None)
def load(name):
    with gzip.open(DATA / (name + '.json.gz'), 'rt', encoding='utf-8') as f:
        return json.load(f)

def cases():
    with gzip.open(DATA / 'cases.csv.gz', 'rt', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def write_csv(path, rows):
    rows = list(rows)
    if not rows:
        return
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
NORMALIZE = lru_cache(maxsize=200000)(resolver.normalize_text)

@lru_cache(maxsize=200000)
def normalize_apostrophe(value):
    return NORMALIZE(str(value or '').replace('’', "'"))

def prepare(config, historical=False):
    schema, apostrophe, conference, pacific = map(int, config)
    rules = json.loads((DATA / 'rules.json').read_text())
    registry = copy.deepcopy(load('historical')['registry'])
    if conference:
        rules['source_type_mapping']['conference-paper'] = 'proceedings-article'
    if pacific:
        row = copy.deepcopy(next((x for x in registry if x['focal_openalex_id'] == 'https://openalex.org/I119942576' and x['decision'] == 'SUPPORTED')))
        row.update(alias_text='University of Pacific', required_context='Stockton')
        registry.append(row)
    resolver.load_rules = lambda path=None: rules
    resolver.load_registry = lambda path=None: registry
    resolver.normalize_text = normalize_apostrophe if apostrophe else NORMALIZE

    def classify(work, institution, evidence):
        ev = copy.deepcopy(evidence)
        if schema:
            for row in ev.get('author_affiliations', []):
                kind = {'Europe PMC': 'external_europe_pmc', 'Crossref': 'external_crossref'}.get(row.get('source'), 'external_structured') if historical else 'external_crossref'
                row.update(text=row.get('affiliation', ''), author=row.get('author_name', 'external_author'), source_kind=kind)
        return resolver.classify(work, institution, ev)
    return classify
