import re
import urllib.parse
import pglast

template_fragment_pattern = re.compile(r"\$\{.*?\}")

text = 'select%20i.item_code%2C%20i.item_name%2C%20bw.u.wu_id%2C%20bu.wu_code%2C%20bu.wu_name%20from%20inventory%20i%20join%20warehouse%20w%20on%20i.warehouse_id%20=%20w.warehouse_id%20join%20batch_warn%20bw%20on%20bw.warehouse_id%20=%20w.warehouse_id%20where%20i.status%20=%20%27%27active%27%27'
decoded = urllib.parse.unquote(text)
print('Decoded:', decoded)

cleaned = template_fragment_pattern.sub("NULL", decoded)
print('Cleaned:', cleaned)

# Test parsing
try:
    parsed = pglast.parse_sql(cleaned)
    print('Parse OK')
except Exception as e:
    print('Parse error:', e)