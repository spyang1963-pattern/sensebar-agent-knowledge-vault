import yt_dlp
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

script_dir = os.path.dirname(os.path.abspath(__file__))
keywords = ["claude", "codex", "antigravity", "opencode", "agent", "googlea"]

all_entries = []
for tab in ['videos', 'streams']:
    url = 'https://www.youtube.com/@sensebar/' + tab
    ydl_opts = {'extract_flat': True, 'skip_download': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get('entries', [])
        all_entries.extend(entries)
        print(tab + ' 分頁: ' + str(len(entries)) + ' 支')
    except Exception as e:
        print('提取 ' + tab + ' 失敗: ' + str(e))

# 去重（同一個 video ID 取第一個）
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

# 輸出過濾清單 sensebar_ai_videos.md
md = '# @sensebar AI Agent 相關影片清單\n\n'
md += '此清單篩選自 YouTube 頻道 [@sensebar](https://www.youtube.com/@sensebar) 中與 **Claude AI**、**Codex**、**AntiGravity**、**OpenCode**、**AI Agent** 及 **Google AI** 相關的影片。\n\n'
md += '**篩選關鍵字：** ' + ', '.join(keywords) + '\n\n'
md += '| 影片標題 | 網址 | 匹配關鍵字 |\n'
md += '| --- | --- | --- |\n'
for m in matches:
    escaped = m['title'].replace('|', '\\|')
    md += '| ' + escaped + ' | [' + m['url'] + '](' + m['url'] + ') | ' + ', '.join(m['matched']) + ' |\n'

out_path = os.path.join(script_dir, 'sensebar_ai_videos.md')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(md)
print('儲存過濾清單至: ' + out_path)

# 輸出全部清單 sensebar_all_videos.md
all_md = '# @sensebar 頻道全部影片清單（含直播）\n\n'
all_md += '| # | 標題 | 網址 |\n'
all_md += '| --- | --- | --- |\n'
for i, entry in enumerate(unique_entries, 1):
    title = entry.get('title', '')
    vid = entry.get('id', '')
    url_full = 'https://www.youtube.com/watch?v=' + vid
    escaped = title.replace('|', '\\|')
    all_md += '| ' + str(i) + ' | ' + escaped + ' | [' + url_full + '](' + url_full + ') |\n'

all_out = os.path.join(script_dir, 'sensebar_all_videos.md')
with open(all_out, 'w', encoding='utf-8') as f:
    f.write(all_md)
print('儲存全部清單至: ' + all_out)

# 輸出 URL 清單 sensebar_ai_urls.txt
urls_path = os.path.join(script_dir, 'sensebar_ai_urls.txt')
with open(urls_path, 'w', encoding='utf-8') as f:
    for m in matches:
        f.write(m['url'] + '\n')
print('儲存 URL 清單（' + str(len(matches)) + ' 筆）至: ' + urls_path)
