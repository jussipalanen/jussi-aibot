"""
Programming language detection for code reviews: by file name first, then by content.

The content rules are plain regular expressions with weights, written so that Python and
JavaScript read them the same way. The code review page gets them in its config and runs the
same detector in the browser, so the language shown while typing matches the review result.
"""
import os
import re

# File name → language. These are also the source files a code rubric accepts.
EXTENSION_LANGUAGES = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".vue": "Vue", ".svelte": "Svelte",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".groovy": "Groovy", ".gradle": "Groovy",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".cs": "C#", ".fs": "F#", ".vb": "Visual Basic",
    ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".m": "Objective-C", ".dart": "Dart",
    ".lua": "Lua", ".pl": "Perl", ".r": "R", ".jl": "Julia",
    ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang", ".hs": "Haskell", ".clj": "Clojure",
    ".ml": "OCaml", ".zig": "Zig", ".sol": "Solidity", ".sql": "SQL",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell", ".bat": "Batch",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "Less",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".xml": "XML",
    ".tf": "Terraform",
}
FILENAME_LANGUAGES = {"dockerfile": "Dockerfile", "makefile": "Makefile", "jenkinsfile": "Groovy"}

_JS = [
    (r"\b(const|let|var) \w+[ \t]*=", 1),
    (r"\bfunction[ \t]*\w*[ \t]*\(", 2),
    (r"=>", 1),
    (r"\bconsole\.\w+\(", 2),
    (r"\brequire\(['\"]", 2),
    (r"^[ \t]*(import .+ from ['\"]|export (default |const |function |class ))", 2),
    (r"\b(document|window)\.\w+", 2),
    (r"===|!==", 1),
]

# Each pattern found adds its weight; the highest total wins. On a tie the earlier rule wins,
# so JavaScript comes before TypeScript (which also counts the JavaScript patterns).
#
# The patterns run on untrusted input of up to 100 000 characters, on the server and on every
# keystroke in the browser, so they must not backtrack badly: they stay within one line
# ([ \t] instead of \s, [^)\n] instead of .*) and never nest or chain overlapping repeats.
LANGUAGE_RULES = [
    {"language": "Python", "flags": "m", "patterns": [
        (r"^[ \t]*def \w+\([^)\n]*\)[^:\n]*:[ \t]*$", 3),
        (r"^[ \t]*(from [\w.]+ import [\w*, ()]+|import [\w.]+( as \w+)?[ \t]*)$", 2),
        (r"^[ \t]*class \w+(\([^)\n]*\))?:[ \t]*$", 3),
        (r"\bself\.\w+", 2),
        (r"^[ \t]*(elif|except|finally|with)\b[^\n]*:[ \t]*$", 2),
        (r"__name__ == ['\"]__main__['\"]", 3),
        (r"\b(None|True|False)\b", 1),
        (r"\bprint\(", 1),
    ]},
    {"language": "JavaScript", "flags": "m", "patterns": _JS},
    {"language": "TypeScript", "flags": "m", "patterns": [
        (r"^[ \t]*(export )?(interface|type) \w+(<[^>\n]*>)?[ \t]*(=|\{)", 3),
        (r"\w[ \t]*:[ \t]*(string|number|boolean|any|unknown|void|never)\b", 3),
        (r"\bas (const|string|number|any|unknown)\b", 2),
        (r"^[ \t]*(public|private|protected|readonly) \w+[ \t]*[:(]", 1),
        *_JS,
    ]},
    {"language": "Java", "flags": "m", "patterns": [
        (r"\bpublic static void main[ \t]*\(String", 5),
        (r"\bSystem\.(out|err)\.print", 4),
        (r"^[ \t]*package [\w.]+;", 4),
        (r"^[ \t]*import (static )?[\w.]+(\.\*)?;", 3),
        (r"^[ \t]*(public |private |protected )?(abstract |final )?class \w+", 1),
        (r"@(Override|Autowired|\w+Mapping)\b", 2),
        (r"\b(String|int|boolean|void|List<\w+>) \w+[ \t]*[=;(]", 1),
    ]},
    {"language": "Kotlin", "flags": "m", "patterns": [
        (r"^[ \t]*(private |override |suspend )*fun \w+\(", 4),
        (r"\bval \w+[ \t]*[:=]", 2),
        (r"^[ \t]*package [\w.]+[ \t]*$", 2),
        (r"\bdata class\b", 3),
        (r"\bprintln\(", 1),
    ]},
    {"language": "C#", "flags": "m", "patterns": [
        (r"^[ \t]*using System(\.\w+)*;", 5),
        (r"\bConsole\.Write(Line)?\(", 4),
        (r"\{ get; (private |init; )?(set; )?\}", 4),
        (r"\bpublic (async |static )*(Task|void|string|int|bool)(<[^>\n]*>)? \w+\(", 2),
        (r"^[ \t]*namespace [\w.]+", 2),
    ]},
    {"language": "C", "flags": "m", "patterns": [
        (r"^[ \t]*#include[ \t]*<\w+\.h>", 3),
        (r"\bprintf\(", 2),
        (r"\bint main[ \t]*\(", 2),
        (r"\b(malloc|free|sizeof)\(", 2),
    ]},
    {"language": "C++", "flags": "m", "patterns": [
        (r"^[ \t]*#include[ \t]*<(iostream|vector|string|map|memory|algorithm)>", 4),
        (r"\bstd::\w+", 4),
        (r"\b(cout|cerr)[ \t]*<<|\bcin[ \t]*>>", 4),
        (r"\btemplate[ \t]*<", 3),
        (r"^[ \t]*#include", 1),
    ]},
    {"language": "Go", "flags": "m", "patterns": [
        (r"^[ \t]*package \w+[ \t]*$", 2),
        (r"^[ \t]*func (\(\w+ \*?\w+\) )?\w+\(", 4),
        (r"\bfmt\.\w+\(", 4),
        (r"\bif err != nil\b", 5),
        (r"^[ \t]*import \($", 3),
        (r":=", 2),
    ]},
    {"language": "Rust", "flags": "m", "patterns": [
        (r"^[ \t]*(pub )?fn \w+(<[^>\n]*>)?\(", 4),
        (r"\blet mut \w+", 4),
        (r"\b(println|vec|format)!", 4),
        (r"^[ \t]*use \w+(::\w+)+", 3),
        (r"^[ \t]*impl\b", 3),
        (r"&str\b|\b(Option|Result)<", 2),
    ]},
    {"language": "PHP", "flags": "m", "patterns": [
        (r"<\?php", 6),
        (r"\$\w+[ \t]*=", 2),
        (r"\bfunction \w+\(\$", 3),
        (r"^[ \t]*namespace [\w\\]+;", 3),
        (r"->\w+\(", 1),
    ]},
    {"language": "Ruby", "flags": "m", "patterns": [
        (r"^[ \t]*def \w+[?!]?(\([^)\n]*\))?[ \t]*$", 3),
        (r"^[ \t]*end[ \t]*$", 2),
        (r"\bdo \|\w+(, \w+)*\|", 4),
        (r"^[ \t]*require ['\"]", 2),
        (r"\bputs\b", 2),
        (r"\.each\b", 1),
    ]},
    {"language": "Swift", "flags": "m", "patterns": [
        (r"^[ \t]*import (UIKit|SwiftUI|Foundation)\b", 5),
        (r"\b(guard|if) let\b", 4),
        (r"\bfunc \w+\([^)\n]*\)( -> \w+\??)? \{", 2),
        (r"\bvar \w+: \w+", 2),
    ]},
    {"language": "SQL", "flags": "im", "patterns": [
        (r"^[ \t]*(SELECT|INSERT INTO|UPDATE \w+ SET|DELETE FROM|CREATE (TABLE|INDEX|VIEW)|ALTER TABLE|DROP TABLE)\b", 4),
        (r"\b(FROM \w+|WHERE|JOIN|GROUP BY|ORDER BY)\b", 2),
    ]},
    {"language": "Shell", "flags": "m", "patterns": [
        (r"^#![^\n]*\b(ba|z)?sh\b", 6),
        (r"^[ \t]*(if \[|fi$|then$|done$|esac$)", 3),
        (r"^[ \t]*(echo|export|cd|sudo|apt|apt-get|curl|grep) ", 2),
        (r"\$\{?\w+\}?", 1),
    ]},
    {"language": "HTML", "flags": "im", "patterns": [
        (r"<!doctype html>|<html\b", 6),
        (r"<(div|span|p|a|body|head|script|section|ul|li)\b[^>]*>", 3),
        (r"</\w+>", 1),
    ]},
    {"language": "CSS", "flags": "m", "patterns": [
        # A selector line: each repeat starts with exactly one separator, so there is one way to match.
        (r"^[ \t]*[.#]?[\w-]+([ ,>+~:.#][\w-]*)*\{[ \t]*$", 2),
        (r"^[ \t]*[\w-]+[ \t]*:[^;\n]+;[ \t]*$", 2),
        (r"@media\b|!important\b", 3),
    ]},
    {"language": "JSON", "flags": "m", "patterns": [
        (r"^[ \t]*\"[^\"\n]+\"[ \t]*:", 3),
        (r"^[ \t]*[\[{][ \t]*$", 1),
    ]},
    {"language": "YAML", "flags": "m", "patterns": [
        (r"^---[ \t]*$", 3),
        (r"^[\w-]+:[ \t]*$", 1),
        (r"^[ \t]*- [\w\"']", 1),
        (r"^[ \t]*[\w-]+: [^{};\n]+$", 1),
    ]},
    {"language": "Dockerfile", "flags": "im", "patterns": [
        (r"^FROM [\w./-]+(:[\w.-]+)?( AS \w+)?[ \t]*$", 4),
        (r"^(RUN|COPY|WORKDIR|ENTRYPOINT|CMD|EXPOSE|ENV) ", 3),
    ]},
]
# The lowest total that counts as a detection, so a single weak hint is not enough.
MIN_LANGUAGE_SCORE = 2

_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE}
_COMPILED = [
    (rule["language"], [
        (re.compile(source, sum(_FLAGS[flag] for flag in rule["flags"])), weight)
        for source, weight in rule["patterns"]
    ])
    for rule in LANGUAGE_RULES
]


def language_for_filename(filename: str) -> str | None:
    """The language a file name (or path) implies, e.g. `src/app.py` → Python."""
    name = os.path.basename(filename.lower())
    return FILENAME_LANGUAGES.get(name) or EXTENSION_LANGUAGES.get(os.path.splitext(name)[1])


def detect_language(code: str, filename: str | None = None) -> str | None:
    """The file name's language, or the language the code looks most like, or None."""
    if filename and (language := language_for_filename(filename)):
        return language
    best, best_score = None, 0
    for language, patterns in _COMPILED:
        score = sum(weight for pattern, weight in patterns if pattern.search(code))
        if score > best_score:
            best, best_score = language, score
    return best if best_score >= MIN_LANGUAGE_SCORE else None


def browser_config() -> dict:
    """What the code review page needs to run the same detector in the browser."""
    return {
        "extensionLanguages": EXTENSION_LANGUAGES,
        "filenameLanguages": FILENAME_LANGUAGES,
        "languageRules": [
            {"language": rule["language"], "flags": rule["flags"], "patterns": [list(p) for p in rule["patterns"]]}
            for rule in LANGUAGE_RULES
        ],
        "minLanguageScore": MIN_LANGUAGE_SCORE,
    }
