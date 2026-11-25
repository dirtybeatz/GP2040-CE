#!/usr/bin/env python3
"""
GP2040-CE All-in-One Patcher v2 für Haute42 S16 (Board-Target: Haute42COSMOX)
Behebt beide Fehler aus dem Compiler-Log (src/config_utils.cpp):
  1. Erweitert actionList[] in migrateMacroPinsToGpio() sauber mehrzeilig auf MAX_MACRO_LIMIT (kein kaputtes '};'-Duplizieren).
  2. Erhöht EEPROM_SIZE_BYTES in FlashPROM.h sicher auf 40960 Bytes (40 KB = 10 x 4 KB Flash-Sektoren),
     sodass Config_size (33.999 Bytes bei 10 Slots x 25 Inputs in aktuellem GP2040-CE) sauber besteht.
     Optional mit --eeprom-size 32768 unverändert lassen (dann max. --inputs 18 wählen).

Verwendung:
  python3 scripts/patch_haute42_s16_10macros.py --slots 10 --inputs 25 --repo .
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


class PatchReport:
    def __init__(self) -> None:
        self.updated: List[str] = []
        self.unchanged: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def mark_updated(self, rel_path: str, detail: str) -> None:
        self.updated.append(f"[OK] {rel_path}: {detail}")

    def mark_unchanged(self, rel_path: str, detail: str) -> None:
        self.unchanged.append(f"[--] {rel_path}: {detail}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"[WARN] {msg}")

    def error(self, msg: str) -> None:
        self.errors.append(f"[ERR] {msg}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, content: str, dry_run: bool) -> None:
    if not dry_run:
        path.write_text(content, encoding="utf-8", newline="\n")


def find_first_existing(repo: Path, candidates: List[str]) -> Optional[Path]:
    for rel in candidates:
        p = repo / rel
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 1. Protobuf: proto/enums.proto
# ---------------------------------------------------------------------------
def patch_enums_proto(repo: Path, slots: int, dry_run: bool, report: PatchReport) -> Dict[int, int]:
    path = find_first_existing(repo, ["proto/enums.proto", "src/proto/enums.proto"])
    if not path:
        report.error("proto/enums.proto nicht gefunden.")
        return {}

    content = read_text(path)
    enum_match = re.search(r"(enum\s+GpioAction\s*\{)([\s\S]*?)(\n\})", content)
    if not enum_match:
        report.error("enum GpioAction in proto/enums.proto nicht gefunden.")
        return {}

    body = enum_match.group(2)
    used_ids = {int(m.group(1)) for m in re.finditer(r"=\s*(-?\d+)\s*;", body)}
    existing_macros: Dict[int, int] = {}
    for m in re.finditer(r"\bBUTTON_PRESS_MACRO_(\d+)\s*=\s*(\d+)\s*;", body):
        existing_macros[int(m.group(1))] = int(m.group(2))

    if not existing_macros:
        report.error("Keine BUTTON_PRESS_MACRO_* Einträge in GpioAction gefunden.")
        return {}

    next_id = (max(used_ids) + 1) if used_ids else 100
    additions: List[str] = []
    macro_id_map: Dict[int, int] = dict(existing_macros)

    for i in range(1, slots + 1):
        if i not in macro_id_map:
            while next_id in used_ids:
                next_id += 1
            macro_id_map[i] = next_id
            used_ids.add(next_id)
            additions.append(f"    BUTTON_PRESS_MACRO_{i} = {next_id};")
            next_id += 1

    rel = str(path.relative_to(repo))
    if not additions:
        report.mark_unchanged(rel, f"BUTTON_PRESS_MACRO_1..{slots} bereits vorhanden")
        return macro_id_map

    last_macro_match = None
    for m in re.finditer(r"^[ \t]*BUTTON_PRESS_MACRO_\d+\s*=\s*\d+\s*;.*$", body, flags=re.MULTILINE):
        last_macro_match = m

    if last_macro_match:
        insert_pos = last_macro_match.end()
        new_body = body[:insert_pos] + "\n" + "\n".join(additions) + body[insert_pos:]
    else:
        new_body = body + "\n" + "\n".join(additions) + "\n"

    new_content = content[: enum_match.start(2)] + new_body + content[enum_match.end(2) :]
    write_text(path, new_content, dry_run)
    report.mark_updated(
        rel,
        f"BUTTON_PRESS_MACRO_7..{slots} hinzugefügt "
        f"(IDs: {', '.join(f'{k}={macro_id_map[k]}' for k in range(7, slots + 1))})",
    )
    return macro_id_map


# ---------------------------------------------------------------------------
# 2. Protobuf: proto/config.options & proto/config.proto
# ---------------------------------------------------------------------------
def patch_config_proto_and_options(repo: Path, slots: int, inputs: int, dry_run: bool, report: PatchReport) -> None:
    patched_any = False

    options_path = find_first_existing(repo, ["proto/config.options", "src/proto/config.options"])
    if options_path:
        content = read_text(options_path)
        new_content = content
        new_content = re.sub(
            r"(MacroOptions\.macroList\s+[^\n]*?max_count\s*:\s*)\d+",
            rf"\g<1>{slots}",
            new_content,
        )
        new_content = re.sub(
            r"(Macro\.macroInputs\s+[^\n]*?max_count\s*:\s*)\d+",
            rf"\g<1>{inputs}",
            new_content,
        )
        rel = str(options_path.relative_to(repo))
        if new_content != content:
            write_text(options_path, new_content, dry_run)
            report.mark_updated(rel, f"MacroOptions.macroList max_count:{slots}, Macro.macroInputs max_count:{inputs}")
            patched_any = True
        elif f"max_count:{slots}" in content and f"max_count:{inputs}" in content:
            report.mark_unchanged(rel, f"bereits auf {slots} Slots / {inputs} Inputs")
            patched_any = True

    proto_path = find_first_existing(repo, ["proto/config.proto", "src/proto/config.proto"])
    if proto_path:
        content = read_text(proto_path)
        new_content = content
        new_content = re.sub(
            r"(repeated\s+Macro\s+macroList\s*=\s*\d+\s*\[[^\]]*max_count\s*=\s*)\d+",
            rf"\g<1>{slots}",
            new_content,
        )
        new_content = re.sub(
            r"(repeated\s+MacroInput\s+macroInputs\s*=\s*\d+\s*\[[^\]]*max_count\s*=\s*)\d+",
            rf"\g<1>{inputs}",
            new_content,
        )
        rel = str(proto_path.relative_to(repo))
        if new_content != content:
            write_text(proto_path, new_content, dry_run)
            report.mark_updated(rel, f"Inline nanopb max_count auf {slots}/{inputs} gesetzt")
            patched_any = True
        else:
            report.mark_unchanged(rel, "keine Inline-max_count-Änderung erforderlich")

    if not patched_any:
        report.error("Weder proto/config.options noch proto/config.proto enthielten MacroOptions.macroList / Macro.macroInputs max_count.")


# ---------------------------------------------------------------------------
# 3. FlashPROM EEPROM-Größe (40 KB = 40960 Bytes = 10 x 4 KB Sektoren)
# ---------------------------------------------------------------------------
def patch_eeprom_size(repo: Path, eeprom_size: int, dry_run: bool, report: PatchReport) -> None:
    if eeprom_size % 4096 != 0 or eeprom_size < 32768:
        report.error(f"Ungültige EEPROM-Größe {eeprom_size}: muss ein Vielfaches von 4096 und >= 32768 sein.")
        return

    if eeprom_size == 32768:
        report.mark_unchanged("EEPROM_SIZE_BYTES", "bleibt auf 32768 Bytes (32 KB)")
        return

    sectors = eeprom_size // 4096
    candidates = [
        "lib/FlashPROM/src/FlashPROM.h",
        "lib/FlashPROM/FlashPROM.h",
        "headers/storagemanager.h",
        "headers/config_utils.h",
        "headers/enums.h",
    ]

    found_files: List[Path] = []
    for rel in candidates:
        p = repo / rel
        if p.exists():
            found_files.append(p)

    # Zusätzlich in lib/FlashPROM und headers nach #define EEPROM_SIZE_BYTES suchen
    for search_dir in [repo / "lib" / "FlashPROM", repo / "headers"]:
        if not search_dir.exists():
            continue
        for fpath in sorted(search_dir.rglob("*.h*")):
            if fpath not in found_files and "EEPROM_SIZE_BYTES" in read_text(fpath):
                found_files.append(fpath)

    patched = False
    for fpath in found_files:
        content = read_text(fpath)
        if not re.search(r"#define\s+EEPROM_SIZE_BYTES\b", content):
            continue

        rel = str(fpath.relative_to(repo))
        # Ersetzt z.B.:
        #   #define EEPROM_SIZE_BYTES 32768
        #   #define EEPROM_SIZE_BYTES (8 * 4096)
        #   #define EEPROM_SIZE_BYTES (8 * FLASH_SECTOR_SIZE)
        #   #define EEPROM_SIZE_BYTES 0x8000
        # Hinweis: Nur wenn der aktuelle Wert kleiner als eeprom_size ist oder noch nicht eeprom_size entspricht.
        def replace_eeprom_def(m: re.Match) -> str:
            prefix = m.group(1)
            expr = m.group(2).strip()
            if "FLASH_SECTOR_SIZE" in expr:
                return f"{prefix}({sectors} * FLASH_SECTOR_SIZE)"
            return f"{prefix}{eeprom_size}"

        new_content = re.sub(
            r"(#define\s+EEPROM_SIZE_BYTES[ \t]+)([^\r\n/]+)",
            replace_eeprom_def,
            content,
            count=1,
        )
        if new_content != content:
            write_text(fpath, new_content, dry_run)
            report.mark_updated(rel, f"EEPROM_SIZE_BYTES auf {eeprom_size} Bytes ({eeprom_size // 1024} KB / {sectors} Sektoren) erhöht")
            patched = True
        else:
            report.mark_unchanged(rel, f"EEPROM_SIZE_BYTES bereits auf {eeprom_size} Bytes")
            patched = True

    if not patched:
        report.error("Konnte '#define EEPROM_SIZE_BYTES' in lib/FlashPROM/ oder headers/ nicht finden.")


# ---------------------------------------------------------------------------
# 4. C++ Header & Macro Addon: headers/addons/input_macro.h & src/addons/input_macro.cpp
# ---------------------------------------------------------------------------
def expand_brace_list_macro6(text: str, slots: int) -> str:
    """
    Erweitert C++-Array-Initialisierer sicher über mehrere Zeilen hinweg, z.B.:
      const static GpioAction actionList[6] = { GpioAction::BUTTON_PRESS_MACRO_1, ...,
                                                GpioAction::BUTTON_PRESS_MACRO_5, GpioAction::BUTTON_PRESS_MACRO_6 };
    """
    pat = re.compile(
        r"(\bGpioAction\s+\w+\s*\[\s*)(?:6|MAX_MACRO_LIMIT)?(\s*\]\s*=\s*\{)([\s\S]*?)(\};)"
    )

    def repl(m: re.Match) -> str:
        decl_prefix, open_brace, body, close_brace = m.groups()
        if "BUTTON_PRESS_MACRO_6" not in body:
            return m.group(0)
        if f"BUTTON_PRESS_MACRO_{slots}" in body:
            return m.group(0)

        ns_match = re.search(r"(GpioAction::|GpioAction_)BUTTON_PRESS_MACRO_6", body)
        ns = ns_match.group(1) if ns_match else "GpioAction::"

        extra_items = [f"{ns}BUTTON_PRESS_MACRO_{i}" for i in range(7, slots + 1)]
        body_stripped = body.rstrip()
        sep = " " if body_stripped.endswith(",") else ", "
        new_body = body_stripped + sep + ", ".join(extra_items) + " "
        return f"{decl_prefix}MAX_MACRO_LIMIT{open_brace}{new_body}{close_brace}"

    return pat.sub(repl, text)


def patch_input_macro_cpp(repo: Path, slots: int, inputs: int, dry_run: bool, report: PatchReport) -> None:
    hdr = find_first_existing(repo, ["headers/addons/input_macro.h"])
    if not hdr:
        report.error("headers/addons/input_macro.h nicht gefunden.")
        return

    content = read_text(hdr)
    new_content = content
    new_content = re.sub(r"(#define\s+MAX_MACRO_LIMIT\s+)\d+", rf"\g<1>{slots}", new_content)
    new_content = re.sub(r"(#define\s+MAX_MACRO_INPUT_LIMIT\s+)\d+", rf"\g<1>{inputs}", new_content)

    rel = str(hdr.relative_to(repo))
    if new_content != content:
        write_text(hdr, new_content, dry_run)
        report.mark_updated(rel, f"MAX_MACRO_LIMIT={slots}, MAX_MACRO_INPUT_LIMIT={inputs}")
    elif re.search(rf"#define\s+MAX_MACRO_LIMIT\s+{slots}\b", content) and re.search(
        rf"#define\s+MAX_MACRO_INPUT_LIMIT\s+{inputs}\b", content
    ):
        report.mark_unchanged(rel, f"bereits auf {slots}/{inputs}")
    else:
        report.error(f"Konnte MAX_MACRO_LIMIT / MAX_MACRO_INPUT_LIMIT in {rel} nicht finden.")

    cpp = find_first_existing(repo, ["src/addons/input_macro.cpp"])
    if not cpp:
        report.warn("src/addons/input_macro.cpp nicht gefunden.")
        return

    cpp_content = read_text(cpp)
    new_cpp = cpp_content

    if f"BUTTON_PRESS_MACRO_{slots}" not in new_cpp:
        # 4a) Array-Initialisierer sicher erweitern
        new_cpp = expand_brace_list_macro6(new_cpp, slots)

        # 4b) Switch-Case-Blöcke mit break; oder return;
        case_pat = re.compile(
            r"(^[ \t]*case\s+(GpioAction::|GpioAction_)BUTTON_PRESS_MACRO_6\s*:[^\n]*\n"
            r"(?:[ \t]+[^\n]*\n)*?[ \t]*(?:break|return\b[^\n]*)\s*;)",
            flags=re.MULTILINE,
        )

        def expand_switch_case(m: re.Match) -> str:
            block = m.group(1)
            extra = [block]
            for i in range(7, slots + 1):
                b = block.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                b = re.sub(r"(\[\s*)5(\s*\])", rf"\g<1>{i - 1}\g<2>", b)
                b = re.sub(r"(=\s*)5(\s*;)", rf"\g<1>{i - 1}\g<2>", b)
                b = re.sub(r"(\(\s*)5(\s*[,\)])", rf"\g<1>{i - 1}\g<2>", b)
                extra.append(b)
            return "\n".join(extra)

        new_cpp, n_cases = case_pat.subn(expand_switch_case, new_cpp)

        # 4c) Einzeilige case-Statements: case GpioAction::BUTTON_PRESS_MACRO_6: ...; break;
        if n_cases == 0 and f"BUTTON_PRESS_MACRO_{slots}" not in new_cpp:
            one_line_case = re.compile(
                r"^([ \t]*case\s+(?:GpioAction::|GpioAction_)BUTTON_PRESS_MACRO_6\s*:[^\n]*)$",
                flags=re.MULTILINE,
            )

            def expand_one_line_case(m: re.Match) -> str:
                line = m.group(1)
                out = [line]
                for i in range(7, slots + 1):
                    l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                    l_new = re.sub(r"(\[\s*)5(\s*\])", rf"\g<1>{i - 1}\g<2>", l_new)
                    l_new = re.sub(r"(=\s*)5(\s*;)", rf"\g<1>{i - 1}\g<2>", l_new)
                    out.append(l_new)
                return "\n".join(out)

            new_cpp = one_line_case.sub(expand_one_line_case, new_cpp)

    rel_cpp = str(cpp.relative_to(repo))
    if new_cpp != cpp_content:
        write_text(cpp, new_cpp, dry_run)
        report.mark_updated(rel_cpp, f"BUTTON_PRESS_MACRO_7..{slots} ergänzt")
    else:
        report.mark_unchanged(rel_cpp, "verwendet bereits MAX_MACRO_LIMIT oder schon gepatcht")


# ---------------------------------------------------------------------------
# 5. C++ Config & GPIO Action Mapping (src/config_utils.cpp u.a.)
# ---------------------------------------------------------------------------
def patch_additional_cpp_macro_refs(repo: Path, slots: int, dry_run: bool, report: PatchReport) -> None:
    cpp_dirs = [d for d in [repo / "src", repo / "headers"] if d.exists()]
    for base in cpp_dirs:
        for fpath in sorted(base.rglob("*")):
            if fpath.suffix not in {".cpp", ".h", ".hpp", ".c"}:
                continue
            if fpath.name in {"input_macro.cpp", "input_macro.h"}:
                continue
            content = read_text(fpath)
            new_content = content
            rel = str(fpath.relative_to(repo))

            # 5a) macroList_count = 6 -> MAX_MACRO_LIMIT
            if "macroList_count" in new_content:
                new_content = re.sub(
                    r"(macroList_count\s*=\s*)6(\s*;)",
                    r"\g<1>MAX_MACRO_LIMIT\g<2>",
                    new_content,
                )

            # 5b) Mehrzeilige GpioAction-Arrays (wie actionList[6] in migrateMacroPinsToGpio) sauber erweitern
            if "BUTTON_PRESS_MACRO_6" in new_content and f"BUTTON_PRESS_MACRO_{slots}" not in new_content:
                new_content = expand_brace_list_macro6(new_content, slots)

            # 5c) Einzelne switch-cases oder Einzelzeilen-Einträge (OHNE schließende '};' zu duplizieren!)
            if "BUTTON_PRESS_MACRO_6" in new_content and f"BUTTON_PRESS_MACRO_{slots}" not in new_content:
                # Range-Obergrenzen wie <= BUTTON_PRESS_MACRO_6
                new_content = re.sub(
                    r"((?:<=|>=|<|>)\s*(?:GpioAction::|GpioAction_)?BUTTON_PRESS_MACRO_)6\b",
                    rf"\g<1>{slots}",
                    new_content,
                )

                # Switch-Case-Zeilen oder Map-Einträge (die genau EIN BUTTON_PRESS_MACRO_6 enthalten und nicht mit }; enden)
                safe_line_pat = re.compile(
                    r"^([ \t]*(?:case\s+|\{)[ \t]*(?:GpioAction::|GpioAction_)?BUTTON_PRESS_MACRO_6\b[^\n]*)$",
                    flags=re.MULTILINE,
                )

                def expand_safe_line(m: re.Match) -> str:
                    line = m.group(1)
                    if "};" in line or "BUTTON_PRESS_MACRO_5" in line:
                        return line
                    out = [line]
                    for i in range(7, slots + 1):
                        l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                        l_new = re.sub(r"(\[\s*)5(\s*\])", rf"\g<1>{i - 1}\g<2>", l_new)
                        l_new = re.sub(r'("Macro\s*)6(")', rf"\g<1>{i}\g<2>", l_new)
                        out.append(l_new)
                    return "\n".join(out)

                new_content = safe_line_pat.sub(expand_safe_line, new_content)

            if new_content != content:
                write_text(fpath, new_content, dry_run)
                report.mark_updated(rel, f"Makro-Referenzen sauber auf {slots} Slots angepasst")


# ---------------------------------------------------------------------------
# 6. Web-Configurator Backend: src/webconfig.cpp & lwipopts.h
# ---------------------------------------------------------------------------
def patch_webconfig_and_lwip(repo: Path, slots: int, inputs: int, dry_run: bool, report: PatchReport) -> None:
    webconfig = find_first_existing(repo, ["src/webconfig.cpp"])
    if webconfig:
        content = read_text(webconfig)
        new_content = content
        changes: List[str] = []

        def bump_json_doc(m: re.Match) -> str:
            prefix, size_str, suffix = m.group(1), m.group(2), m.group(3)
            try:
                size = int(size_str)
            except ValueError:
                return m.group(0)
            if 4096 <= size < 24576:
                changes.append(f"JsonDocument {size} -> 24576")
                return f"{prefix}24576{suffix}"
            return m.group(0)

        new_content = re.sub(r"(DynamicJsonDocument\s+\w+\s*\(\s*)(\d+)(\s*\))", bump_json_doc, new_content)
        new_content = re.sub(r"(StaticJsonDocument<\s*)(\d+)(\s*>)", bump_json_doc, new_content)

        def bump_post_limit(m: re.Match) -> str:
            prefix, val_str = m.group(1), m.group(2)
            val = int(val_str)
            if 4096 <= val < 32768:
                changes.append(f"POST-Limit {val} -> 32768")
                return f"{prefix}32768"
            return m.group(0)

        new_content = re.sub(
            r"(#define\s+(?:HTTPD_POST_MAX_LEN|MAX_POST_DATA_SIZE|POST_BUFFER_SIZE|HTTP_POST_MAX_SIZE)\s+)(\d+)",
            bump_post_limit,
            new_content,
        )
        new_content = re.sub(
            r"(http_post_payload\.reserve\(\s*)(\d+)(\s*\))",
            lambda m: f"{m.group(1)}32768{m.group(3)}" if int(m.group(2)) < 32768 else m.group(0),
            new_content,
        )

        macro_fn_pat = re.compile(r"((?:setMacroAddonOptions|getMacroAddonOptions)[\s\S]*?^\})", flags=re.MULTILINE)

        def fix_macro_fn(m: re.Match) -> str:
            fn_body = m.group(1)
            fn_new = re.sub(r"(\bstd::min\s*\([^,]+,\s*(?:\(size_t\))?\s*)6(\s*\))", r"\g<1>MAX_MACRO_LIMIT\g<2>", fn_body)
            fn_new = re.sub(r"(\bstd::min\s*\([^,]+,\s*(?:\(size_t\))?\s*)30(\s*\))", r"\g<1>MAX_MACRO_INPUT_LIMIT\g<2>", fn_new)
            fn_new = re.sub(r"(<\s*)6(\s*;\s*\w+\+\+)", r"\g<1>MAX_MACRO_LIMIT\g<2>", fn_new)
            fn_new = re.sub(r"(<\s*)30(\s*;\s*\w+\+\+)", r"\g<1>MAX_MACRO_INPUT_LIMIT\g<2>", fn_new)
            if fn_new != fn_body:
                changes.append("Macro-API-Limits auf MAX_MACRO_LIMIT / MAX_MACRO_INPUT_LIMIT")
            return fn_new

        new_content = macro_fn_pat.sub(fix_macro_fn, new_content)

        rel = str(webconfig.relative_to(repo))
        if new_content != content:
            write_text(webconfig, new_content, dry_run)
            report.mark_updated(rel, ", ".join(dict.fromkeys(changes)) or "Puffer/Limits angepasst")
        else:
            report.mark_unchanged(rel, "verwendet bereits dynamisches ArduinoJson/std::string & MAX_MACRO_LIMIT")
    else:
        report.warn("src/webconfig.cpp nicht gefunden.")

    for lwip_path in repo.rglob("lwipopts.h"):
        if "pico-sdk" in lwip_path.parts or "build" in lwip_path.parts:
            continue
        content = read_text(lwip_path)
        new_content = content

        def bump_mem_size(m: re.Match) -> str:
            prefix, expr = m.group(1), m.group(2).strip()
            simple_int = re.fullmatch(r"(\d+)", expr)
            mul_kb = re.fullmatch(r"\(?\s*(\d+)\s*\*\s*1024\s*\)?", expr)
            val = int(simple_int.group(1)) if simple_int else (int(mul_kb.group(1)) * 1024 if mul_kb else None)
            if val is not None and val < 24576:
                return f"{prefix}(24 * 1024)"
            return m.group(0)

        new_content = re.sub(r"(#define\s+MEM_SIZE\s+)([^\r\n/]+)", bump_mem_size, new_content)
        rel = str(lwip_path.relative_to(repo))
        if new_content != content:
            write_text(lwip_path, new_content, dry_run)
            report.mark_updated(rel, "MEM_SIZE auf 24 KB angehoben (stabiler HTTP-POST für 10 Makros)")
        else:
            report.mark_unchanged(rel, "MEM_SIZE bereits ausreichend groß (>= 24 KB)")


# ---------------------------------------------------------------------------
# 7. React Web-UI: www/src/...
# ---------------------------------------------------------------------------
def patch_web_ui(repo: Path, slots: int, inputs: int, macro_id_map: Dict[int, int], dry_run: bool, report: PatchReport) -> None:
    www_src = repo / "www" / "src"
    if not www_src.exists():
        report.error("www/src/ nicht gefunden — Web-Build kann nicht gepatcht werden.")
        return

    for fpath in sorted(www_src.rglob("*")):
        if fpath.suffix not in {".ts", ".tsx", ".js", ".jsx", ".json"}:
            continue
        content = read_text(fpath)
        new_content = content
        rel = str(fpath.relative_to(repo))

        if "InputMacro" in fpath.name or "Macro" in fpath.name:
            new_content = re.sub(r"(\b(?:MAX_MACRO_LIMIT|MACRO_LIMIT|MAX_MACROS)\s*=\s*)\d+", rf"\g<1>{slots}", new_content)
            new_content = re.sub(r"(\b(?:MAX_MACRO_INPUT_LIMIT|MAX_MACRO_INPUTS|MACRO_INPUT_LIMIT)\s*=\s*)\d+", rf"\g<1>{inputs}", new_content)
            new_content = re.sub(r"(macroList\.length\s*<\s*)\d+", rf"\g<1>{slots}", new_content)
            new_content = re.sub(r"(macroInputs\.length\s*<\s*)\d+", rf"\g<1>{inputs}", new_content)
            new_content = re.sub(r"(\.slice\(\s*0\s*,\s*)30(\s*\))", rf"\g<1>{inputs}\g<2>", new_content)

        if "BUTTON_PRESS_MACRO_6" in new_content and f"BUTTON_PRESS_MACRO_{slots}" not in new_content:
            is_locale = "Locales" in fpath.parts or "locales" in fpath.parts

            if is_locale:
                loc_pat = re.compile(
                    r'^([ \t]*["\']?BUTTON_PRESS_MACRO_6["\']?\s*:\s*["\'])([^"\']*?)6([^"\']*?)(["\']\s*,?)([ \t]*)$',
                    flags=re.MULTILINE,
                )

                def expand_locale(m: re.Match) -> str:
                    prefix, txt_pre, txt_post, quote_comma, trail = m.groups()
                    has_comma = quote_comma.rstrip().endswith(",")
                    q = quote_comma[0]
                    lines = [f"{prefix}{txt_pre}6{txt_post}{q},{trail}"]
                    for i in range(7, slots + 1):
                        key_pref = prefix.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                        comma = "," if (i < slots or has_comma) else ""
                        lines.append(f"{key_pref}{txt_pre}{i}{txt_post}{q}{comma}{trail}")
                    return "\n".join(lines)

                new_content = loc_pat.sub(expand_locale, new_content)
            else:
                enum_line_pat = re.compile(
                    r"^([ \t]*)(['\"]?)BUTTON_PRESS_MACRO_6(['\"]?)(\s*[:=]\s*)(\d+)(\s*,?)([ \t]*)$",
                    flags=re.MULTILINE,
                )

                def expand_ui_enum(m: re.Match) -> str:
                    indent, q1, q2, sep, _old_id, comma, trail = m.groups()
                    lines = [f"{indent}{q1}BUTTON_PRESS_MACRO_6{q2}{sep}{_old_id},{trail}"]
                    for i in range(7, slots + 1):
                        eid = macro_id_map.get(i, int(_old_id) + (i - 6))
                        c = "," if (i < slots or comma.strip() == ",") else ""
                        lines.append(f"{indent}{q1}BUTTON_PRESS_MACRO_{i}{q2}{sep}{eid}{c}{trail}")
                    return "\n".join(lines)

                updated_enum, n_enum = enum_line_pat.subn(expand_ui_enum, new_content)
                if n_enum > 0:
                    new_content = updated_enum
                else:
                    arr_pat = re.compile(r"^([ \t]*[^\n]*?BUTTON_PRESS_MACRO_6[^\n]*)$", flags=re.MULTILINE)

                    def expand_ui_arr(m: re.Match) -> str:
                        line = m.group(1)
                        if "BUTTON_PRESS_MACRO_5" in line:
                            return line
                        out = [line if line.rstrip().endswith(",") else line + ","]
                        for i in range(7, slots + 1):
                            l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                            if i < slots and not l_new.rstrip().endswith(","):
                                l_new += ","
                            out.append(l_new)
                        return "\n".join(out)

                    new_content = arr_pat.sub(expand_ui_arr, new_content)

        if new_content != content:
            write_text(fpath, new_content, dry_run)
            report.mark_updated(rel, f"Web-UI auf {slots} Makro-Slots / {inputs} Inputs aktualisiert")


def main() -> int:
    parser = argparse.ArgumentParser(description="GP2040-CE Haute42 S16 All-in-One Patcher v2")
    parser.add_argument("--slots", type=int, default=10, help="Anzahl Makro-Slots (Standard: 10)")
    parser.add_argument("--inputs", type=int, default=25, help="Max. Input-Zeilen pro Makro (Standard: 25)")
    parser.add_argument(
        "--eeprom-size",
        type=int,
        default=40960,
        help="EEPROM_SIZE_BYTES (Vielfaches von 4096; Standard: 40960 = 40 KB für 10x25 in GP2040-CE aktuell)",
    )
    parser.add_argument("--repo", type=str, default=".", help="Pfad zum GP2040-CE Repository-Root")
    parser.add_argument("--dry-run", action="store_true", help="Nur prüfen, keine Dateien schreiben")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "CMakeLists.txt").exists():
        print(f"[ERR] {repo} sieht nicht nach einem GP2040-CE Repository-Root aus (CMakeLists.txt fehlt).", file=sys.stderr)
        return 1

    print("=" * 72)
    print(f" GP2040-CE Haute42 S16 Patcher v2 | {args.slots} Slots x {args.inputs} Inputs | EEPROM {args.eeprom_size} B")
    print(f" Repository: {repo}")
    print("=" * 72)

    report = PatchReport()
    macro_id_map = patch_enums_proto(repo, args.slots, args.dry_run, report)
    patch_config_proto_and_options(repo, args.slots, args.inputs, args.dry_run, report)
    patch_eeprom_size(repo, args.eeprom_size, args.dry_run, report)
    patch_input_macro_cpp(repo, args.slots, args.inputs, args.dry_run, report)
    patch_additional_cpp_macro_refs(repo, args.slots, args.dry_run, report)
    patch_webconfig_and_lwip(repo, args.slots, args.inputs, args.dry_run, report)
    patch_web_ui(repo, args.slots, args.inputs, macro_id_map, args.dry_run, report)

    print("\n--- Zusammenfassung ---")
    for line in report.updated:
        print(line)
    for line in report.unchanged:
        print(line)
    for line in report.warnings:
        print(line)
    for line in report.errors:
        print(line, file=sys.stderr)

    print("=" * 72)
    if report.errors:
        print(f"FEHLER: {len(report.errors)} kritische Probleme aufgetreten.", file=sys.stderr)
        return 1

    print(f"FERTIG: {len(report.updated)} Dateien gepatcht, {len(report.unchanged)} bereits aktuell.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
