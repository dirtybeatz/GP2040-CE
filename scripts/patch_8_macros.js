import fs from 'fs';
import path from 'path';

const TARGET_MACROS = 8;

function walk(dir, files = []) {
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (['node_modules', 'dist', 'build', '.git'].includes(entry.name)) continue;
      walk(full, files);
    } else {
      files.push(full);
    }
  }
  return files;
}

function patchFile(filePath, replacer, required = false) {
  if (!fs.existsSync(filePath)) {
    if (required) throw new Error(`❌ Pflichtdatei nicht gefunden: ${filePath}`);
    console.warn(`⚠️ Übersprungen (nicht gefunden): ${filePath}`);
    return false;
  }
  const original = fs.readFileSync(filePath, 'utf8');
  const updated = replacer(original);
  if (original !== updated) {
    fs.writeFileSync(filePath, updated, 'utf8');
    console.log(`✅ Gepatcht: ${filePath}`);
    return true;
  }
  if (required) {
    throw new Error(`❌ Patch hat in Pflichtdatei nicht gegriffen: ${filePath}`);
  }
  return false;
}

// ---------------------------------------------------------------------------
// 1. headers/addons/input_macro.h -> MAX_MACRO_LIMIT = 8
// ---------------------------------------------------------------------------
patchFile(
  'headers/addons/input_macro.h',
  (content) =>
    content.replace(/#define\s+MAX_MACRO_LIMIT\s+\d+/, `#define MAX_MACRO_LIMIT ${TARGET_MACROS}`),
  true
);

// ---------------------------------------------------------------------------
// 2. proto/config.options -> MacroOptions.macroList max_count:8
// ---------------------------------------------------------------------------
patchFile(
  'proto/config.options',
  (content) =>
    content.replace(/(MacroOptions\.macroList\s+max_count:)\d+/, `$1${TARGET_MACROS}`),
  true
);

// ---------------------------------------------------------------------------
// 3. proto/enums.proto -> Freie Enum-IDs in GpioAction ermitteln & eintragen
// ---------------------------------------------------------------------------
let macro7Id = null;
let macro8Id = null;

patchFile(
  'proto/enums.proto',
  (content) => {
    const enumMatch = content.match(/enum\s+GpioAction\s*\{([\s\S]*?)\}/);
    if (!enumMatch) throw new Error('❌ enum GpioAction in proto/enums.proto nicht gefunden!');

    const enumBlock = enumMatch[0];
    const enumBody = enumMatch[1];

    if (enumBody.includes('BUTTON_PRESS_MACRO_7')) {
      const m7 = enumBody.match(/BUTTON_PRESS_MACRO_7\s*=\s*(\d+)/);
      const m8 = enumBody.match(/BUTTON_PRESS_MACRO_8\s*=\s*(\d+)/);
      macro7Id = Number(m7[1]);
      macro8Id = Number(m8[1]);
      return content;
    }

    const ids = [...enumBody.matchAll(/=\s*(\d+)\s*;/g)].map((m) => Number(m[1]));
    const maxId = Math.max(...ids);
    macro7Id = maxId + 1;
    macro8Id = maxId + 2;

    console.log(`ℹ️ Ermittelte GpioAction IDs -> MACRO_7=${macro7Id}, MACRO_8=${macro8Id}`);

    const updatedBlock = enumBlock.replace(
      /\}\s*$/,
      `    BUTTON_PRESS_MACRO_7 = ${macro7Id};\n    BUTTON_PRESS_MACRO_8 = ${macro8Id};\n}`
    );

    return content.replace(enumBlock, updatedBlock);
  },
  true
);

// ---------------------------------------------------------------------------
// 4. src/addons/input_macro.cpp -> Trigger-Pins für Macro 7 & 8 ergänzen
// ---------------------------------------------------------------------------
patchFile(
  'src/addons/input_macro.cpp',
  (content) => {
    if (content.includes('BUTTON_PRESS_MACRO_7')) return content;

    let updated = content;

    // Muster A: Eigener case-Block mit Index 5 und break;
    const caseBlockRegex =
      /([ \t]*case\s+GpioAction::BUTTON_PRESS_MACRO_6\s*:[\s\S]*?break;)/g;
    if (caseBlockRegex.test(updated)) {
      updated = updated.replace(caseBlockRegex, (block) => {
        const block7 = block
          .replace(/BUTTON_PRESS_MACRO_6/g, 'BUTTON_PRESS_MACRO_7')
          .replace(/\[5\]/g, '[6]')
          .replace(/\(\s*5\s*\)/g, '(6)')
          .replace(/=\s*5\s*;/g, '= 6;');
        const block8 = block
          .replace(/BUTTON_PRESS_MACRO_6/g, 'BUTTON_PRESS_MACRO_8')
          .replace(/\[5\]/g, '[7]')
          .replace(/\(\s*5\s*\)/g, '(7)')
          .replace(/=\s*5\s*;/g, '= 7;');
        return `${block}\n${block7}\n${block8}`;
      });
    } else {
      // Muster B: Liste / Fallthrough / Array mit GpioAction::BUTTON_PRESS_MACRO_6
      updated = updated.replace(
        /(GpioAction::BUTTON_PRESS_MACRO_6)/g,
        '$1,\n        GpioAction::BUTTON_PRESS_MACRO_7,\n        GpioAction::BUTTON_PRESS_MACRO_8'
      );
    }

    // Sicherheits-Check gegen direkte Enum-Differenzrechnung (action - BUTTON_PRESS_MACRO_1)
    if (updated.includes('BUTTON_PRESS_MACRO_1') && /-\s*GpioAction::BUTTON_PRESS_MACRO_1/.test(updated)) {
      console.warn(
        '⚠️ Hinweis: Enum-Subtraktion in input_macro.cpp erkannt – bitte Build-Log prüfen!'
      );
    }

    return updated;
  },
  true
);

// Kontroll-Scan: Gibt weitere Vorkommen in src/ & headers/ im CI-Log aus
for (const file of [...walk('src'), ...walk('headers')]) {
  if (file.endsWith('input_macro.cpp') || file.endsWith('input_macro.h')) continue;
  const text = fs.readFileSync(file, 'utf8');
  if (text.includes('BUTTON_PRESS_MACRO_6')) {
    console.log(`🔎 Weiterer Fund in C++ (${file}) – wird automatisch erweitert...`);
    patchFile(file, (content) => {
      if (content.includes('BUTTON_PRESS_MACRO_7')) return content;
      return content.replace(
        /(case\s+GpioAction::BUTTON_PRESS_MACRO_6\s*:)/g,
        '$1\n        case GpioAction::BUTTON_PRESS_MACRO_7:\n        case GpioAction::BUTTON_PRESS_MACRO_8:'
      );
    });
  }
}

// ---------------------------------------------------------------------------
// 5. Web-UI (www/src) -> Macro-Limit, Enum-Mapping & Übersetzungen
// ---------------------------------------------------------------------------
const webFiles = walk('www/src');
let patchedMacroUi = false;
let patchedPinEnum = false;

for (const file of webFiles) {
  if (!/\.(ts|tsx|js|jsx)$/.test(file)) continue;
  const original = fs.readFileSync(file, 'utf8');
  let updated = original;

  // 5a) Macro-Limit in InputMacroAddonPage & zugehörigen Komponenten
  if (
    file.includes('InputMacro') ||
    /MAX_MACRO_LIMIT/.test(updated) ||
    /macroList\.length\s*[<>]=?\s*6/.test(updated)
  ) {
    updated = updated
      .replace(/(MAX_MACRO_LIMIT\s*=\s*)\d+/g, `$1${TARGET_MACROS}`)
      .replace(/(macroList\.length\s*<\s*)6\b/g, `$1${TARGET_MACROS}`)
      .replace(/(macroList\.length\s*>=\s*)6\b/g, `$1${TARGET_MACROS}`)
      .replace(/(macroList\.length\s*===?\s*)6\b/g, `$1${TARGET_MACROS}`);
    if (updated !== original) patchedMacroUi = true;
  }

  // 5b) Numerische GpioAction-Definitionen (z. B. www/src/Data/Pins.ts)
  if (
    updated.includes('BUTTON_PRESS_MACRO_6') &&
    !updated.includes('BUTTON_PRESS_MACRO_7')
  ) {
    // Key: Number (z.B. BUTTON_PRESS_MACRO_6: 46,)
    if (/BUTTON_PRESS_MACRO_6\s*:\s*\d+/.test(updated)) {
      updated = updated.replace(
        /([ \t]*BUTTON_PRESS_MACRO_6\s*:\s*\d+,?)/g,
        `$1\n\tBUTTON_PRESS_MACRO_7: ${macro7Id},\n\tBUTTON_PRESS_MACRO_8: ${macro8Id},`
      );
      patchedPinEnum = true;
    }

    // Key: String (Locale-Dateien wie en/PinMapping.jsx, de-DE/PinMapping.jsx etc.)
    if (/BUTTON_PRESS_MACRO_6\s*:\s*['"][^'"]+['"]/.test(updated)) {
      updated = updated.replace(
        /([ \t]*)(['"]?BUTTON_PRESS_MACRO_6['"]?\s*:\s*(['"])([^'"]*?)6([^'"]*?)\3,?)/g,
        (_, indent, full, quote, prefix, suffix) =>
          `${indent}${full}\n${indent}BUTTON_PRESS_MACRO_7: ${quote}${prefix}7${suffix}${quote},\n${indent}BUTTON_PRESS_MACRO_8: ${quote}${prefix}8${suffix}${quote},`
      );
    }

    // Array / Enum-Referenzen (z.B. BUTTON_ACTIONS.BUTTON_PRESS_MACRO_6)
    if (
      /BUTTON_PRESS_MACRO_6(?![\w'":])/.test(updated) &&
      !updated.includes('BUTTON_PRESS_MACRO_7')
    ) {
      updated = updated.replace(
        /([ \t]*)([\w.]*BUTTON_PRESS_MACRO_6)(,?)/g,
        (_, indent, ref, comma) => {
          const ref7 = ref.replace('MACRO_6', 'MACRO_7');
          const ref8 = ref.replace('MACRO_6', 'MACRO_8');
          const c = comma || ',';
          return `${indent}${ref}${c}\n${indent}${ref7}${c}\n${indent}${ref8}${comma}`;
        }
      );
    }
  }

  if (updated !== original) {
    fs.writeFileSync(file, updated, 'utf8');
    console.log(`✅ Web-UI gepatcht: ${file}`);
  }
}

if (!patchedMacroUi) {
  throw new Error('❌ Macro-Limit in der Web-UI (www/src) wurde nicht gefunden!');
}
if (!patchedPinEnum) {
  console.warn('⚠️ Hinweis: Numerisches BUTTON_PRESS_MACRO_6-Mapping in www/src prüfen.');
}

console.log(`🚀 Fertig! 8 Makro-Slots (IDs ${macro7Id} & ${macro8Id}) komplett eingepatcht.`);
