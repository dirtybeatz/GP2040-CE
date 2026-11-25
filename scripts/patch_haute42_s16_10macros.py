#!/usr/bin/env python3
"""
GP2040-CE All-in-One Patcher für Haute42 S16 (Board-Target: Haute42COSMOX)
Stabile Konfiguration:
  - 10 Makro-Slots (MAX_MACRO_LIMIT = 10)
  - 25 Input-Zeilen pro Slot (MAX_MACRO_INPUT_LIMIT = 25)
  - Bleibt sicher im 32-KB-EEPROM (kein riskanter 64-KB-Flash-Partition-Hack nötig)
  - Erhöht JSON-/HTTP-POST-Puffer in webconfig.cpp & lwipopts.h für 10 volle Makros
  - Patcht Protobuf, C++-Firmware, React Web-UI & Lokalisierungen konsistent & idempotent

Verwendung:
  python3 scripts/patch_haute42_s16_10macros.py
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
    """
    Erweitert enum GpioAction um BUTTON_PRESS_MACRO_7 .. BUTTON_PRESS_MACRO_<slots>.
    Vergibt kollisionsfrei die nächsten freien Enum-IDs und gibt das Mapping {slot_num: enum_id} zurück.
    """
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

    # Bestehende Enum-IDs sammeln, um Kollisionen mit neueren v0.7.12-Aktionen zu vermeiden
    used_ids = {int(m.group(1)) for m in re.finditer(r"=\s*(\d+)\s*;", body)}
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

    # Direkt nach dem letzten BUTTON_PRESS_MACRO_X Eintrag einfügen
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
        f"BUTTON_PRESS_MACRO_{min(int(a.split('MACRO_')[1].split()[0]) for a in additions)}..{slots} hinzugefügt "
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
        # Unterstützt Inline-Nanopb-Optionen wie: repeated Macro macroList = 2 [(nanopb).max_count = 6];
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
# 3. C++ Header & Macro Addon: headers/addons/input_macro.h & src/addons/input_macro.cpp
# ---------------------------------------------------------------------------
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

    # 3a) Switch-Case-Erweiterung (falls BUTTON_PRESS_MACRO_1..6 als switch/case implementiert sind)
    if f"BUTTON_PRESS_MACRO_{slots}" not in new_cpp:
        case_pat = re.compile(
            r"(^[ \t]*case\s+(GpioAction::|GpioAction_)BUTTON_PRESS_MACRO_6\s*:[^\n]*\n"
            r"(?:[ \t]+[^\n]*\n)*?[ \t]*break\s*;)",
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

        # Pattern 2: Einzelzeilen / Array-Initialisierer / if-else mit BUTTON_PRESS_MACRO_6
        if n_cases == 0:
            line_pat = re.compile(
                r"^([ \t]*[^\n]*?(?:GpioAction::|GpioAction_)BUTTON_PRESS_MACRO_6[^\n]*)$",
                flags=re.MULTILINE,
            )

            def expand_line(m: re.Match) -> str:
                line = m.group(1)
                is_array_item = (
                    not line.rstrip().endswith(";")
                    and not line.rstrip().endswith("{")
                    and not line.rstrip().endswith(")")
                )
                lines = [line + ("," if is_array_item and not line.rstrip().endswith(",") else "")]
                for i in range(7, slots + 1):
                    l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                    l_new = re.sub(r"(\[\s*)5(\s*\])", rf"\g<1>{i - 1}\g<2>", l_new)
                    l_new = re.sub(r"(=\s*)5(\s*;)", rf"\g<1>{i - 1}\g<2>", l_new)
                    if is_array_item and i < slots and not l_new.rstrip().endswith(","):
                        l_new = l_new + ","
                    lines.append(l_new)
                return "\n".join(lines)

            new_cpp = line_pat.sub(expand_line, new_cpp)

    rel_cpp = str(cpp.relative_to(repo))
    if new_cpp != cpp_content:
        write_text(cpp, new_cpp, dry_run)
        report.mark_updated(rel_cpp, f"BUTTON_PRESS_MACRO_7..{slots} ergänzt")
    else:
        report.mark_unchanged(rel_cpp, "verwendet bereits MAX_MACRO_LIMIT oder schon gepatcht")


# ---------------------------------------------------------------------------
# 4. C++ Config & GPIO Action Mapping (config_utils.cpp, gp2040.cpp, etc.)
# ---------------------------------------------------------------------------
def patch_additional_cpp_macro_refs(repo: Path, slots: int, dry_run: bool, report: PatchReport) -> None:
    """
    Sucht im gesamten src/- und headers/-Verzeichnis nach weiteren Stellen, an denen
    BUTTON_PRESS_MACRO_6 explizit aufgeführt ist (z.B. GpioAction-Tabellen, pin_mappings),
    sowie nach macroList_count = 6 in config_utils.cpp.
    """
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

            # 4a) macroList_count = 6 -> MAX_MACRO_LIMIT (z.B. in src/config_utils.cpp)
            if "macroList_count" in new_content:
                new_content = re.sub(
                    r"(macroList_count\s*=\s*)6(\s*;)",
                    r"\g<1>MAX_MACRO_LIMIT\g<2>",
                    new_content,
                )

            # 4b) Weitere BUTTON_PRESS_MACRO_6 Aufzählungen in C++
            if "BUTTON_PRESS_MACRO_6" in new_content and f"BUTTON_PRESS_MACRO_{slots}" not in new_content:
                line_pat = re.compile(
                    r"^([ \t]*[^\n]*?BUTTON_PRESS_MACRO_6[^\n]*)$",
                    flags=re.MULTILINE,
                )

                def expand_cpp_ref(m: re.Match) -> str:
                    line = m.group(1)
                    if re.search(r"(<=|>=|==|!=|<|>)\s*(?:GpioAction::|GpioAction_)?BUTTON_PRESS_MACRO_6", line):
                        return re.sub(
                            r"((?:<=|>=|<|>)\s*(?:GpioAction::|GpioAction_)?BUTTON_PRESS_MACRO_)6\b",
                            rf"\g<1>{slots}",
                            line,
                        )
                    out = [line]
                    for i in range(7, slots + 1):
                        l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                        l_new = re.sub(r"(\[\s*)5(\s*\])", rf"\g<1>{i - 1}\g<2>", l_new)
                        l_new = re.sub(r'("Macro\s*)6(")', rf"\g<1>{i}\g<2>", l_new)
                        out.append(l_new)
                    return "\n".join(out)

                new_content = line_pat.sub(expand_cpp_ref, new_content)

            if new_content != content:
                write_text(fpath, new_content, dry_run)
                report.mark_updated(rel, f"Makro-Referenzen auf {slots} Slots angepasst")


# ---------------------------------------------------------------------------
# 5. Web-Configurator Backend: src/webconfig.cpp & lwipopts.h
#    Verhindert JSON-Truncation / RP2040-Reboot beim Speichern von 10 vollen Makros
# ---------------------------------------------------------------------------
def patch_webconfig_and_lwip(repo: Path, slots: int, inputs: int, dry_run: bool, report: PatchReport) -> None:
    webconfig = find_first_existing(repo, ["src/webconfig.cpp"])
    if webconfig:
        content = read_text(webconfig)
        new_content = content
        changes: List[str] = []

        # 5a) DynamicJsonDocument / StaticJsonDocument Kapazität im Webconfig-POST prüfen
        # Bei 10 Slots x 25 Inputs beträgt der JSON-Payload ~10-14 KB -> >= 24576 Bytes absichern
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

        new_content = re.sub(
            r"(DynamicJsonDocument\s+\w+\s*\(\s*)(\d+)(\s*\))",
            bump_json_doc,
            new_content,
        )
        new_content = re.sub(
            r"(StaticJsonDocument<\s*)(\d+)(\s*>)",
            bump_json_doc,
            new_content,
        )

        # 5b) Falls http_post_payload / POST-Längenlimit hart auf < 32768 begrenzt ist
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

        # 5c) Hardcodierte Schleifengrenzen in setMacroAddonOptions / getMacroAddonOptions prüfen
        macro_fn_pat = re.compile(
            r"((?:setMacroAddonOptions|getMacroAddonOptions)[\s\S]*?^\})",
            flags=re.MULTILINE,
        )

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

    # 5d) lwipopts.h: MEM_SIZE für größere HTTP-POST-Pakete (10 volle Makros) absichern
    lwip_candidates = list(repo.rglob("lwipopts.h"))
    for lwip_path in lwip_candidates:
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
# 6. React Web-UI: www/src/...
# ---------------------------------------------------------------------------
def patch_web_ui(repo: Path, slots: int, inputs: int, macro_id_map: Dict[int, int], dry_run: bool, report: PatchReport) -> None:
    www_src = repo / "www" / "src"
    if not www_src.exists():
        report.error("www/src/ nicht gefunden — Web-Build kann nicht gepatcht werden.")
        return

    ui_macro_patched = False
    ui_pins_patched = False

    for fpath in sorted(www_src.rglob("*")):
        if fpath.suffix not in {".ts", ".tsx", ".js", ".jsx", ".json"}:
            continue
        content = read_text(fpath)
        new_content = content
        rel = str(fpath.relative_to(repo))

        # 6a) InputMacro-Seite / Addon-Komponente (Slots & Input-Zeilen)
        if "InputMacro" in fpath.name or "Macro" in fpath.name:
            new_content = re.sub(
                r"(\b(?:MAX_MACRO_LIMIT|MACRO_LIMIT|MAX_MACROS)\s*=\s*)\d+",
                rf"\g<1>{slots}",
                new_content,
            )
            new_content = re.sub(
                r"(\b(?:MAX_MACRO_INPUT_LIMIT|MAX_MACRO_INPUTS|MACRO_INPUT_LIMIT)\s*=\s*)\d+",
                rf"\g<1>{inputs}",
                new_content,
            )
            new_content = re.sub(
                r"(macroList\.length\s*<\s*)\d+",
                rf"\g<1>{slots}",
                new_content,
            )
            new_content = re.sub(
                r"(macroInputs\.length\s*<\s*)\d+",
                rf"\g<1>{inputs}",
                new_content,
            )
            new_content = re.sub(
                r"(\.slice\(\s*0\s*,\s*)30(\s*\))",
                rf"\g<1>{inputs}\g<2>",
                new_content,
            )
            if new_content != content:
                ui_macro_patched = True

        # 6b) Pin-Mapping-Enums (BUTTON_PRESS_MACRO_6 -> 7..slots mit exakten Protobuf-IDs)
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
                    ui_pins_patched = True
                else:
                    arr_pat = re.compile(
                        r"^([ \t]*[^\n]*?BUTTON_PRESS_MACRO_6[^\n]*)$",
                        flags=re.MULTILINE,
                    )

                    def expand_ui_arr(m: re.Match) -> str:
                        line = m.group(1)
                        out = [line if line.rstrip().endswith(",") else line + ","]
                        for i in range(7, slots + 1):
                            l_new = line.replace("BUTTON_PRESS_MACRO_6", f"BUTTON_PRESS_MACRO_{i}")
                            if i < slots and not l_new.rstrip().endswith(","):
                                l_new += ","
                            out.append(l_new)
                        return "\n".join(out)

                    new_content = arr_pat.sub(expand_ui_arr, new_content)
                    ui_pins_patched = True

        if new_content != content:
            write_text(fpath, new_content, dry_run)
            report.mark_updated(rel, f"Web-UI auf {slots} Makro-Slots / {inputs} Inputs aktualisiert")

    if not ui_macro_patched:
        report.warn("In www/src/ wurden keine neuen MAX_MACRO_LIMIT-Änderungen geschrieben (evtl. bereits auf 10/25).")
    if not ui_pins_patched:
        report.warn("In www/src/ wurden keine neuen BUTTON_PRESS_MACRO_7..10 Pin-Enums geschrieben (evtl. bereits vorhanden).")


# ---------------------------------------------------------------------------
# 7. EEPROM-Größenabschätzung & Plausibilitätsprüfung
# ---------------------------------------------------------------------------
def check_eeprom_safety(repo: Path, slots: int, inputs: int, report: PatchReport) -> None:
    total_inputs = slots * inputs
    if total_inputs > 260:
        report.warn(
            f"Achtung: {slots} x {inputs} = {total_inputs} Input-Zeilen gesamt. "
            "Über ~260 Zeilen kann Config_size das 32-KB-EEPROM-Limit (32768 Bytes) überschreiten! "
            "Empfohlen für Haute42 S16 (32 KB Safe): 10 Slots x 25 Inputs = 250."
        )
    else:
        print(
            f"[INFO] EEPROM-Check: {slots} Slots x {inputs} Inputs = {total_inputs} Einträge gesamt "
            "(sicher innerhalb des 32-KB-EEPROM-Limits ohne Flash-Layout-Änderung)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="GP2040-CE Haute42 S16 All-in-One Patcher (10 Makros x 25 Inputs)")
    parser.add_argument("--slots", type=int, default=10, help="Anzahl der Makro-Slots (Standard: 10)")
    parser.add_argument("--inputs", type=int, default=25, help="Max. Input-Zeilen pro Makro (Standard: 25)")
    parser.add_argument("--repo", type=str, default=".", help="Pfad zum GP2040-CE Repository-Root")
    parser.add_argument("--dry-run", action="store_true", help="Nur prüfen, keine Dateien schreiben")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / "CMakeLists.txt").exists():
        print(f"[ERR] {repo} sieht nicht nach einem GP2040-CE Repository-Root aus (CMakeLists.txt fehlt).", file=sys.stderr)
        return 1

    print("=" * 72)
    print(f" GP2040-CE Haute42 S16 Patcher | {args.slots} Makro-Slots x {args.inputs} Inputs")
    print(f" Repository: {repo}")
    print("=" * 72)

    report = PatchReport()
    check_eeprom_safety(repo, args.slots, args.inputs, report)

    macro_id_map = patch_enums_proto(repo, args.slots, args.dry_run, report)
    patch_config_proto_and_options(repo, args.slots, args.inputs, args.dry_run, report)
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
