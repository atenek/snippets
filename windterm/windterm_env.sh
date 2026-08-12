#!/usr/bin/env bash
#
# Сохранение и загрузка наборов настроек (workspace) WindTerm по проектам/кейсам.
#
# WindTerm хранит все сессии и настройки в одной папке профиля (обычно ".wind").
# Скрипт позволяет сохранять эту папку целиком под именем набора и в дальнейшем
# подменять активный профиль нужным набором перед запуском WindTerm.
#
# ИСПОЛЬЗОВАНИЕ:
#   ./windterm-profiles.sh save <имя>     - сохранить текущие настройки
#   ./windterm-profiles.sh load <имя>     - загрузить настройки и запустить WindTerm
#   ./windterm-profiles.sh list           - показать сохранённые наборы
#
# Перед первым использованием обязательно поправьте переменные WINDTERM_EXE и
# LIVE_PROFILE_DIR ниже под свою систему.
# Реальный путь к профилю можно узнать:
#   - в файле profiles.config рядом с исполняемым файлом WindTerm, либо
#   - в самой программе: Session -> Preferences -> About -> Profile Directory
#
set -euo pipefail

# ==================== НАСТРОЙКИ (отредактируйте под себя) ====================

# Путь к исполняемому файлу WindTerm
WINDTERM_EXE="$HOME/WindTerm/WindTerm"

# Путь к папке профиля, которую реально использует WindTerm сейчас
# (часто это ~/.wind или ~/.config/.wind - проверьте у себя)
LIVE_PROFILE_DIR="$HOME/.wind"

# Папка, где будут храниться сохранённые наборы настроек (по одному на проект)
STORE_ROOT="$HOME/WindTermProfiles"

# ===============================================================================

usage() {
    echo "Использование:"
    echo "  $0 save <имя>   - сохранить текущие настройки WindTerm"
    echo "  $0 load <имя>   - загрузить настройки и запустить WindTerm"
    echo "  $0 list         - показать сохранённые наборы"
    exit 1
}

stop_windterm() {
    if pgrep -x "WindTerm" > /dev/null 2>&1; then
        echo "Закрываю запущенный WindTerm..."
        pkill -x "WindTerm" || true
        for i in $(seq 1 15); do
            pgrep -x "WindTerm" > /dev/null 2>&1 || break
            sleep 1
        done
        if pgrep -x "WindTerm" > /dev/null 2>&1; then
            echo "WindTerm не закрылся, принудительно завершаю..."
            pkill -9 -x "WindTerm" || true
            sleep 1
        fi
    fi
}

save_profile() {
    local name="$1"
    if [[ -z "$name" ]]; then
        echo "Укажите имя набора: $0 save <имя>"
        exit 1
    fi
    if [[ ! -d "$LIVE_PROFILE_DIR" ]]; then
        echo "Не найдена папка профиля WindTerm: $LIVE_PROFILE_DIR"
        echo "Проверьте переменную LIVE_PROFILE_DIR в скрипте."
        exit 1
    fi

    stop_windterm

    local dest="$STORE_ROOT/$name"
    mkdir -p "$dest"

    echo "Сохраняю текущие настройки WindTerm в: $dest"
    rsync -a --delete "$LIVE_PROFILE_DIR"/ "$dest"/

    echo "Готово: набор '$name' сохранён."
}

load_profile() {
    local name="$1"
    if [[ -z "$name" ]]; then
        echo "Укажите имя набора: $0 load <имя>"
        exit 1
    fi

    local src="$STORE_ROOT/$name"
    if [[ ! -d "$src" ]]; then
        echo "Набор '$name' не найден в $STORE_ROOT"
        exit 1
    fi

    stop_windterm

    echo "Загружаю настройки '$name' в: $LIVE_PROFILE_DIR"
    mkdir -p "$LIVE_PROFILE_DIR"
    rsync -a --delete "$src"/ "$LIVE_PROFILE_DIR"/

    if [[ ! -x "$WINDTERM_EXE" ]]; then
        echo "Не найден исполняемый файл WindTerm: $WINDTERM_EXE"
        echo "Проверьте переменную WINDTERM_EXE в скрипте."
        exit 1
    fi

    echo "Запускаю WindTerm с набором '$name'..."
    nohup "$WINDTERM_EXE" > /dev/null 2>&1 &
    disown
}

list_profiles() {
    if [[ ! -d "$STORE_ROOT" ]]; then
        echo "Сохранённых наборов пока нет (папка $STORE_ROOT отсутствует)."
        return
    fi
    local found=0
    for d in "$STORE_ROOT"/*/; do
        [[ -d "$d" ]] || continue
        found=1
        echo "  - $(basename "$d")"
    done
    if [[ "$found" -eq 0 ]]; then
        echo "Сохранённых наборов пока нет."
    fi
}

ACTION="${1:-}"
NAME="${2:-}"

case "$ACTION" in
    save) save_profile "$NAME" ;;
    load) load_profile "$NAME" ;;
    list) list_profiles ;;
    *) usage ;;
esac
