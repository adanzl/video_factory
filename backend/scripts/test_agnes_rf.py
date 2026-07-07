import requests, base64

with open('/tmp/thumb12.jpg', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('ascii')

# 测 response_format 对单张图片的影响
for label, has_rf in [("no_rf", False), ("with_rf", True)]:
    payload = {
        'model': 'agnes-2.0-flash',
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': '图里是什么？输出JSON格式：{"color":"..."}'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
        ]}],
        'max_tokens': 100,
    }
    if has_rf:
        payload['response_format'] = {'type': 'json_object'}

    resp = requests.post(
        'https://apihub.agnes-ai.com/v1/chat/completions',
        headers={'Authorization': 'Bearer ***REMOVED***', 'Content-Type': 'application/json'},
        json=payload,
        timeout=60,
    )
    print(f'{label}: {resp.status_code}', end='')
    if resp.ok:
        c = resp.json()['choices'][0]['message']['content']
        print(f' len={len(c)} -> {c[:80]}')
    else:
        print(f' -> {resp.text[:200]}')

# 测 47 帧 + response_format
print()
print("test 47 frames + response_format...")
content = [{'type': 'text', 'text': '分析这些帧，输出JSON'}]
for _ in range(47):
    content.append({'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}})

payload = {
    'model': 'agnes-2.0-flash',
    'messages': [{'role': 'user', 'content': content}],
    'max_tokens': 500,
    'response_format': {'type': 'json_object'},
}
resp = requests.post(
    'https://apihub.agnes-ai.com/v1/chat/completions',
    headers={'Authorization': 'Bearer ***REMOVED***', 'Content-Type': 'application/json'},
    json=payload,
    timeout=180,
)
print(f'47frames+rf: {resp.status_code}', end='')
if resp.ok:
    c = resp.json()['choices'][0]['message']['content']
    print(f' len={len(c)} -> {c[:100]}')
else:
    print(f' -> {resp.text[:300]}')
