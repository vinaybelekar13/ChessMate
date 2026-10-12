from pathlib import Path
import re

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

start = s.find("async function switchBook")

if start == -1:
    print("SWITCH_BOOK_FUNCTION_NOT_FOUND")
    raise SystemExit

end = s.find("window.switchBook", start)

if end == -1:
    print("SWITCH_BOOK_END_NOT_FOUND")
    raise SystemExit

block = s[start:end]

# ------------------------------------------------------------
# Replace the page reset inside switchBook()
# ------------------------------------------------------------

page_pattern = r'(\bstate\.page\s*=\s*)1\s*;'

if not re.search(page_pattern, block):
    print("SWITCH_BOOK_PAGE_RESET_NOT_FOUND")
    raise SystemExit

block = re.sub(
    page_pattern,
    r'''state.page =
            getSavedBookPage(
                book.id
            );''',
    block,
    count=1
)

# ------------------------------------------------------------
# Replace loadPage(1) inside switchBook()
# ------------------------------------------------------------

load_pattern = r'await\s+loadPage\s*\(\s*1\s*\)\s*;'

if not re.search(load_pattern, block):
    print("SWITCH_BOOK_LOAD_PAGE_NOT_FOUND")
    raise SystemExit

block = re.sub(
    load_pattern,
    '''await loadPage(
            getSavedBookPage(
                BOOK_ID
            )
        );''',
    block,
    count=1
)

s = s[:start] + block + s[end:]

p.write_bytes(s.encode("latin-1"))

print("BOOK_SWITCH_LAST_PAGE_ENABLED")
