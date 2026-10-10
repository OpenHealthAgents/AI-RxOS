import urllib.request

urls = [
    'http://127.0.0.1:8082/healthz',
    'http://127.0.0.1:8082/metrics',
    'http://127.0.0.1:8082/api/v1/papers',
]

for url in urls:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read(2000).decode('utf-8', 'replace')
            print(url)
            print('STATUS', resp.status)
            print(body)
    except Exception as exc:
        print(url, 'ERROR', repr(exc))
