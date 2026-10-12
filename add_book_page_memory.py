from pathlib import Path

p = Path("js/book-reader.js")

data = p.read_bytes()
s = data.decode("latin-1")

if "CHESSMATE BOOK PAGE MEMORY" in s:
    print("BOOK_PAGE_MEMORY_ALREADY_ADDED")
    raise SystemExit

needle = "PAGE / POSITION LOADING"

pos = s.find(needle)

if pos == -1:
    print("PAGE_LOADING_TEXT_NOT_FOUND")
    raise SystemExit

# Insert immediately before the section containing PAGE / POSITION LOADING.
section_start = s.rfind("/*", 0, pos)

if section_start == -1:
    section_start = pos

helper = r'''/* ============================================================
   CHESSMATE BOOK PAGE MEMORY
   Remembers the last page separately for every book.
   ============================================================ */

function getBookPageKey(bookId) {

    return `chessmate:lastPage:${bookId}`;
}


function getSavedBookPage(bookId) {

    if (!bookId) {
        return 1;
    }

    try {

        const saved =
            Number(
                localStorage.getItem(
                    getBookPageKey(bookId)
                )
            );

        return Number.isFinite(saved) &&
            saved >= 1
            ? saved
            : 1;

    } catch (error) {

        console.warn(
            "[ChessMate] Could not read saved book page:",
            error
        );

        return 1;
    }
}


function saveBookPage(bookId, pageNumber) {

    if (!bookId) {
        return;
    }

    try {

        localStorage.setItem(
            getBookPageKey(bookId),
            String(pageNumber)
        );

    } catch (error) {

        console.warn(
            "[ChessMate] Could not save book page:",
            error
        );
    }
}


'''

s = s[:section_start] + helper + s[section_start:]

# Find the state.page assignment inside loadPage().
load_pos = s.find("async function loadPage")

if load_pos == -1:
    print("LOAD_PAGE_FUNCTION_NOT_FOUND")
    raise SystemExit

page_assignment = s.find(
    "state.page",
    load_pos
)

if page_assignment == -1:
    print("LOAD_PAGE_STATE_NOT_FOUND")
    raise SystemExit

semicolon = s.find(";", page_assignment)

if semicolon == -1:
    print("LOAD_PAGE_STATE_END_NOT_FOUND")
    raise SystemExit

insert_at = semicolon + 1

save_code = '''

    saveBookPage(
        BOOK_ID,
        state.page
    );'''

s = s[:insert_at] + save_code + s[insert_at:]

# Change the startup loadPage(1) only.
startup_marker = "loadPage(1);"

startup_pos = s.find(startup_marker)

if startup_pos == -1:
    print("STARTUP_LOAD_PAGE_NOT_FOUND")
    raise SystemExit

s = (
    s[:startup_pos]
    + '''loadPage(
    getSavedBookPage(BOOK_ID)
);'''
    + s[startup_pos + len(startup_marker):]
)

p.write_bytes(s.encode("latin-1"))

print("BOOK_PAGE_MEMORY_ADDED")
