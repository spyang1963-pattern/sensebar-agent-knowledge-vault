import yt_dlp
import os
import sys
import yaml
sys.stdout.reconfigure(encoding='utf-8')

script_dir = os.path.dirname(os.path.abspath(__file__))

# 讀取設定檔
config_path = os.path.join(script_dir, 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

channel_url = config['channel']['url']
keywords = config['channel']['keywords']

print(f'頻道: {channel_url}')
print(f'關鍵字: {", ".join(keywords)}')
print()

all_entries = []
for tab in ['videos', 'streams']:
    url = channel_url + '/' + tab
    ydl_opts = {'extract_flat': True, 'skip_download': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get('entries', [])
        all_entries.extend(entries)
        print(tab + ' 分頁: ' + str(len(entries)) + ' 支')
    except Exception as e:
        print('提取 ' + tab + ' 失敗: ' + str(e))

# 去重
seen_ids = set()
unique_entries = []
for e in all_entries:
    vid = e.get('id', '')
    if vid and vid not in seen_ids:
        seen_ids.add(vid)
        unique_entries.append(e)

print('去重後共 ' + str(len(unique_entries)) + ' 支影片')
print()

matches = []
for entry in unique_entries:
    title = entry.get('title', '')
    video_url = 'https://www.youtube.com/watch?v=' + entry.get('id', '')
    title_lower = title.lower()
    matched_kws = [kw for kw in keywords if kw in title_lower]
    if matched_kws:
        matches.append({'title': title, 'url': video_url, 'matched': matched_kws})

print('匹配 ' + str(len(matches)) + ' 支影片')
print()

# 取得頻道名稱用於檔案名稱
channel_name = channel_url.split('@')[-1] if '@' in channel_url else 'channel'

# 輸出過濾清單
md = f'# @{channel_name} 相關影片清單\n\n'
md += f'此清單篩選自 YouTube 頻道 [@{channel_name}]({channel_url})\n\n'
md += '**篩選關鍵字：** ' + ', '.join(keywords) + '\n\n'
md += '| 影片標題 | 網址 | 匹配關鍵字 |\n'
md += '| --- | --- | --- |\n'
for m in matches:
    escaped = m['title'].replace('|', '\\|')
    md += '| ' + escaped + ' | [' + m['url'] + '](' + m['url'] + ') | ' + ', '.join(m['matched']) + ' |\n'

out_path = os.path.join(script_dir, f'{channel_name}_ai_videos.md')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(md)
print('儲存過濾清單至: ' + out_path)

# 輸出全部清單
all_md = f'# @{channel_name} 頻道全部影片清單（含直播）\n\n'
all_md += '| # | 標題 | 網址 |\n'
all_md += '| --- | --- | --- |\n'
for i, entry in enumerate(unique_entries, 1):
    title = entry.get('title', '')
    vid = entry.get('id', '')
    url_full = 'https://www.youtube.com/watch?v=' + vid
    escaped = title.replace('|', '\\|')
    all_md += '| ' + str(i) + ' | ' + escaped + ' | [' + url_full + '](' + url_full + ') |\n'

all_out = os.path.join(script_dir, f'{channel_name}_all_videos.md')
with open(all_out, 'w', encoding='utf-8') as f:
    f.write(all_md)
print('儲存全部清單至: ' + all_out)

# 輸出 URL 清單
urls_path = os.path.join(script_dir, f'{channel_name}_ai_urls.txt')
with open(urls_path, 'w', encoding='utf-8') as f:
    for m in matches:
        f.write(m['url'] + '\n')
print('儲存 URL 清單（' + str(len(matches)) + ' 筆）至: ' + urls_path)
