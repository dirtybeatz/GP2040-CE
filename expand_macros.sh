#!/usr/bin/env bash
set -e

echo "=== 1. Passe C++ Header an (headers/addons/input_macro.h) ==="
sed -i 's/#define MAX_MACROS 6/#define MAX_MACROS 12/g' headers/addons/input_macro.h

echo "=== 2. Passe Protobuf-Konfiguration an (proto/config.proto & proto/enums.proto) ==="
sed -i 's/(nanopb).max_count = 6/(nanopb).max_count = 12/g' proto/config.proto

if ! grep -q "BUTTON_ACTION_PRESS_MACRO_7" proto/enums.proto; then
  sed -i '/BUTTON_ACTION_PRESS_MACRO_6 = 39;/a \    BUTTON_ACTION_PRESS_MACRO_7 = 40;\n    BUTTON_ACTION_PRESS_MACRO_8 = 41;\n    BUTTON_ACTION_PRESS_MACRO_9 = 42;\n    BUTTON_ACTION_PRESS_MACRO_10 = 43;\n    BUTTON_ACTION_PRESS_MACRO_11 = 44;\n    BUTTON_ACTION_PRESS_MACRO_12 = 45;' proto/enums.proto
fi

echo "=== 3. Passe C++ Logik an (src/addons/input_macro.cpp) ==="
if ! grep -q "BUTTON_ACTION_PRESS_MACRO_7" src/addons/input_macro.cpp; then
  sed -i '/case GpioAction::BUTTON_ACTION_PRESS_MACRO_6:/a \            case GpioAction::BUTTON_ACTION_PRESS_MACRO_7:\n            case GpioAction::BUTTON_ACTION_PRESS_MACRO_8:\n            case GpioAction::BUTTON_ACTION_PRESS_MACRO_9:\n            case GpioAction::BUTTON_ACTION_PRESS_MACRO_10:\n            case GpioAction::BUTTON_ACTION_PRESS_MACRO_11:\n            case GpioAction::BUTTON_ACTION_PRESS_MACRO_12:' src/addons/input_macro.cpp
fi

echo "=== 4. Passe Web-Konfigurator an (www/src/...) ==="
# Maximale Anzahl im Frontend von 6 auf 12 setzen
find www/src -type f \( -name "*Macro*" -o -name "PinMapping*" \) -exec sed -i 's/MAX_MACROS = 6/MAX_MACROS = 12/g' {} +

# Neue Pin-Mapping-Aktionen im Frontend ergänzen
find www/src -type f -name "*.ts*" -o -name "*.js*" | xargs grep -l "BUTTON_ACTION_PRESS_MACRO_6" | while read -r file; do
  if ! grep -q "BUTTON_ACTION_PRESS_MACRO_7" "$file"; then
    sed -i '/BUTTON_ACTION_PRESS_MACRO_6:[[:space:]]*39,\?/a \	BUTTON_ACTION_PRESS_MACRO_7: 40,\n	BUTTON_ACTION_PRESS_MACRO_8: 41,\n	BUTTON_ACTION_PRESS_MACRO_9: 42,\n	BUTTON_ACTION_PRESS_MACRO_10: 43,\n	BUTTON_ACTION_PRESS_MACRO_11: 44,\n	BUTTON_ACTION_PRESS_MACRO_12: 45,' "$file"
  fi
done

echo "=== Fertig! Alle Dateien wurden auf 12 Makro-Slots gepatcht. ==="