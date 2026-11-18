"""Reproduce the numerical analyses from the frozen inputs."""
from pathlib import Path
import argparse, importlib.metadata, json, socket, sys, time
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'code'))
sys.dont_write_bytecode = True

def offline(*args, **kwargs):
    raise RuntimeError('Network access is disabled during reproduction.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['quick', 'core'])
    args = parser.parse_args()
    started = time.perf_counter()
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    from common import write_json
    import historical, institutional, exact, checks
    files = checks.manifest()
    core = args.mode == 'core'
    if core:
        import numpy
        assert numpy.__version__ == '2.3.5', 'Install the pinned NumPy version in requirements.txt.'
    output = ROOT / 'results' if core else None
    if output:
        output.mkdir(exist_ok=True)
    h = historical.run(output)
    print('Historical comparisons and exact evidence requirements: PASS', flush=True)
    i = institutional.run(output, core=core)
    print('Institutional classifications and estimates: PASS', flush=True)
    e = exact.run(i['rows'], output, core=core)
    print('Finite-population bounds: PASS', flush=True)
    verified = checks.results(h, i, e, core=core)
    report = dict(status=args.mode.upper() + '_PASS', seconds=time.perf_counter() - started, network='blocked', verified_payload_files=files, python=sys.version.split()[0], **verified)
    if core:
        report['numpy'] = importlib.metadata.version('numpy')
        report['full_frame_selection'] = i['summary']['frame_verification']
        report['exact_coverage_checks'] = e['summary']['exhaustive_small_population_checks']
        write_json(output / 'verification.json', report)
    print(json.dumps(report, indent=2))
if __name__ == '__main__':
    main()
