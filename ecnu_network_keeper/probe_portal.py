from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_TARGETS = (
    'http://www.gstatic.com/generate_204',
    'http://connect.rom.miui.com/generate_204',
    'http://detectportal.firefox.com/canonical.html',
    'https://login.ecnu.edu.cn/',
)
DEFAULT_USER_AGENT = 'ecnu-network-keeper-probe/1.0'
KEY_PATTERNS = {
    'ac_id': re.compile(r'ac_id[^0-9]*([0-9]+)'),
    'user_ip': re.compile(r'user_ip[^0-9]*([0-9.]+)'),
    'nas_ip': re.compile(r'nas_ip[^0-9]*([0-9.]+)'),
    'theme': re.compile(r'theme[^A-Za-z0-9_-]*([A-Za-z0-9_-]+)'),
}


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class RedirectStep:
    url: str
    status: int
    location: str | None


@dataclass
class ProbeResult:
    start_url: str
    steps: list[RedirectStep]
    final_url: str | None
    final_status: int | None
    headers: dict[str, str]
    body: str
    forms: list[dict[str, Any]]
    detected: dict[str, str]
    error: str | None = None


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._current_form: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or '' for key, value in attrs}
        if tag == 'form':
            self._current_form = {
                'action': attr_map.get('action', ''),
                'method': attr_map.get('method', 'get').lower(),
                'inputs': [],
            }
            self.forms.append(self._current_form)
        elif tag == 'input' and self._current_form is not None:
            self._current_form['inputs'].append(
                {
                    'name': attr_map.get('name', ''),
                    'type': attr_map.get('type', 'text'),
                    'value': attr_map.get('value', ''),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == 'form':
            self._current_form = None


def fetch_url(url: str, timeout: float, max_redirects: int) -> ProbeResult:
    opener = build_opener(NoRedirectHandler())
    steps: list[RedirectStep] = []
    current_url = url

    for _ in range(max_redirects + 1):
        request = Request(current_url, headers={'User-Agent': DEFAULT_USER_AGENT})
        try:
            response = opener.open(request, timeout=timeout)
            try:
                body = response.read().decode('utf-8', errors='replace')
                headers = dict(response.info().items())
                final_url = response.geturl()
                status = response.getcode()
            finally:
                response.close()

            forms = parse_forms(body)
            detected = detect_values(body, final_url)
            return ProbeResult(
                start_url=url,
                steps=steps,
                final_url=final_url,
                final_status=status,
                headers=headers,
                body=body,
                forms=forms,
                detected=detected,
            )
        except HTTPError as exc:
            status = exc.code
            location = exc.headers.get('Location')
            steps.append(RedirectStep(url=current_url, status=status, location=location))
            if location and status in {301, 302, 303, 307, 308}:
                current_url = urljoin(current_url, location)
                exc.close()
                continue

            try:
                body = exc.read().decode('utf-8', errors='replace')
            finally:
                exc.close()
            forms = parse_forms(body)
            detected = detect_values(body, current_url)
            return ProbeResult(
                start_url=url,
                steps=steps,
                final_url=current_url,
                final_status=status,
                headers=dict(exc.headers.items()),
                body=body,
                forms=forms,
                detected=detected,
                error=f'HTTP {status}',
            )
        except URLError as exc:
            return ProbeResult(
                start_url=url,
                steps=steps,
                final_url=None,
                final_status=None,
                headers={},
                body='',
                forms=[],
                detected={},
                error=str(exc.reason),
            )

    return ProbeResult(
        start_url=url,
        steps=steps,
        final_url=current_url,
        final_status=None,
        headers={},
        body='',
        forms=[],
        detected={},
        error=f'redirect limit exceeded after {max_redirects} hops',
    )


def parse_forms(body: str) -> list[dict[str, Any]]:
    parser = FormParser()
    parser.feed(body)
    return parser.forms


def detect_values(body: str, final_url: str | None) -> dict[str, str]:
    detected: dict[str, str] = {}
    combined = body
    if final_url:
        combined += '\n' + final_url
    for key, pattern in KEY_PATTERNS.items():
        match = pattern.search(combined)
        if match:
            detected[key] = match.group(1)
    return detected


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description='Probe the campus portal without a browser')
    parser.add_argument('targets', nargs='*', default=list(DEFAULT_TARGETS), help='URLs to probe')
    parser.add_argument('--timeout', type=float, default=8.0, help='Timeout per request in seconds')
    parser.add_argument('--max-redirects', type=int, default=8, help='Maximum redirect hops to follow')
    parser.add_argument('--save-dir', default=None, help='Directory used to save raw HTML responses')
    return parser


def save_probe_result(save_dir: str, index: int, result: ProbeResult) -> None:
    from pathlib import Path

    target = Path(save_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / f'probe_{index}.html').write_text(result.body, encoding='utf-8')
    metadata = {
        'start_url': result.start_url,
        'steps': [step.__dict__ for step in result.steps],
        'final_url': result.final_url,
        'final_status': result.final_status,
        'headers': result.headers,
        'forms': result.forms,
        'detected': result.detected,
        'error': result.error,
    }
    (target / f'probe_{index}.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')


def print_result(result: ProbeResult, index: int) -> None:
    print(f'=== Probe {index}: {result.start_url} ===')
    if result.steps:
        print('Redirect chain:')
        for step in result.steps:
            suffix = f' -> {step.location}' if step.location else ''
            print(f'- {step.status} {step.url}{suffix}')
    else:
        print('Redirect chain: none')

    print(f'Final URL: {result.final_url}')
    print(f'Final status: {result.final_status}')
    if result.error:
        print(f'Error: {result.error}')

    if result.detected:
        print('Detected values:')
        for key, value in result.detected.items():
            print(f'- {key}: {value}')

    if result.forms:
        print('Forms:')
        for idx, form in enumerate(result.forms, start=1):
            print(f"- form {idx}: method={form['method']} action={form['action']}")
            for field in form['inputs']:
                name = field['name'] or '(unnamed)'
                print(f"  input: type={field['type']} name={name} value={field['value']}")
    else:
        print('Forms: none')

    snippet = result.body[:1200].strip()
    print('HTML snippet:')
    print(snippet if snippet else '(empty)')
    print()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for index, target in enumerate(args.targets, start=1):
        result = fetch_url(target, timeout=args.timeout, max_redirects=args.max_redirects)
        print_result(result, index)
        if args.save_dir:
            save_probe_result(args.save_dir, index, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
