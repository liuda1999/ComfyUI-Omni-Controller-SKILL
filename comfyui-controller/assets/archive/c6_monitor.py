import json, urllib.request, time, sys

prompt_id = sys.argv[1] if len(sys.argv) > 1 else 'f20f716e-2ad6-4a56-94b9-a88862b56de9'
max_wait = int(sys.argv[2]) if len(sys.argv) > 2 else 1800  # 默认30分钟

start = time.time()
while time.time() - start < max_wait:
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:3198/history/{prompt_id}', timeout=15)
        data = json.loads(r.read())
        if prompt_id in data:
            status = data[prompt_id].get('status', {})
            status_str = status.get('status_str', 'unknown')
            elapsed = int(time.time() - start)
            print(f'[{elapsed}s] status: {status_str}')
            if status_str == 'success':
                outputs = data[prompt_id].get('outputs', {})
                for nid, out in outputs.items():
                    if 'gifs' in out or 'images' in out:
                        print(f'  node {nid}: {json.dumps(out, ensure_ascii=False)[:500]}')
                sys.exit(0)
            elif status_str == 'error':
                msgs = status.get('messages', [])
                for m in msgs:
                    if m[0] == 'execution_error':
                        print(f'ERROR: {json.dumps(m[1], ensure_ascii=False)[:1000]}')
                sys.exit(1)
        else:
            # 检查队列
            try:
                r2 = urllib.request.urlopen('http://127.0.0.1:3198/queue', timeout=10)
                q = json.loads(r2.read())
                running = len(q.get('queue_running', []))
                pending = len(q.get('queue_pending', []))
                elapsed = int(time.time() - start)
                print(f'[{elapsed}s] running={running} pending={pending}')
            except:
                pass
    except Exception as e:
        elapsed = int(time.time() - start)
        print(f'[{elapsed}s] query error: {e}')
    time.sleep(15)

print(f'TIMEOUT after {max_wait}s')
sys.exit(2)
