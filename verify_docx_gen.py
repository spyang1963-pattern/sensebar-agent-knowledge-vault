# -*- coding: utf-8 -*-
"""Verify course-note docx (numPr indents, PAGE footer, 華康 eastAsia font)."""
import sys, glob, re, io, zipfile
base = sys.argv[1]
prefix = sys.argv[2]
outp = sys.argv[3]
files = sorted(glob.glob(base + '\\' + prefix + '*.docx'))
out = io.open(outp, 'w', encoding='utf-8')
bad = []
for f in files:
    z = zipfile.ZipFile(f)
    x = z.read('word/document.xml').decode('utf-8')
    n = len(re.findall(r'<w:numPr>', x))
    eastAsia = set(re.findall(r'w:eastAsia="([^"]+)"', x))
    foot = z.read('word/footer1.xml').decode('utf-8') if 'word/footer1.xml' in z.namelist() else ''
    page = 'PAGE' in foot
    has_font = any('\u83ef\u5eb7' in fn for fn in eastAsia)
    ok = 'OK' if (n > 3 and page and has_font) else 'BAD'
    if ok != 'OK':
        bad.append((f, n, page, has_font))
    out.write('%s | numPr=%d | page=%s | font=%s | %s\n' % (ok, n, page, has_font, f.split('\\')[-1]))
out.write('\n=== BAD ===\n')
for b in bad:
    out.write(repr(b) + '\n')
out.write('total=%d bad=%d' % (len(files), len(bad)))
out.close()
print('bad=%d' % len(bad))