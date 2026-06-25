#!/usr/bin/env python3
"""Раскладка SSH-публичного ключа по списку хостов.

Без сторонних зависимостей (только стандартная библиотека).
Подключается к каждому хосту из HOSTS_FILE по паролю (через pty, чтобы
ssh принял пароль), и идемпотентно добавляет PUBLIC_KEY в
~/.ssh/authorized_keys пользователя.

Формат строки в hosts_list.txt:
    host user password [# встроенный комментарий]
Пустые строки и строки, начинающиеся с '#', игнорируются.
Встроенный комментарий (токен с '#' и всё после) отбрасывается.

"""

import fcntl
import os
import pty
import select
import subprocess
import sys
import termios
import time

HOSTS_FILE = "hosts_list.txt"

PUBLIC_KEY = "ssh-ed25519 AAAA**********PUBLIC_KEY**************** alex@i5ubu24"

CONNECT_TIMEOUT = 10
SESSION_TIMEOUT = 30

MARKER_ADDED = "KEY_ADDED_OK"
MARKER_PRESENT = "KEY_ALREADY_PRESENT"

# Удалённый скрипт.
#  - set -e: любой сбой подготовки прерывает выполнение (исправляет проблему
#    приоритета && / ||, из-за которой ключ мог дописываться в неготовый файл);
#  - umask 077: создаваемые файлы сразу с безопасными правами;
#  - дозапись недостающего '\n', чтобы новый ключ не приклеился к последней
#    строке без перевода строки;
#  - grep -qxF: точное совпадение целой строки -> идемпотентность;
#  - в конце печатается маркер, который проверяет питон-сторона.
REMOTE_CMD = f"""
set -eu
umask 077
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
if [ -s ~/.ssh/authorized_keys ] && [ -n "$(tail -c1 ~/.ssh/authorized_keys)" ]; then
    echo >> ~/.ssh/authorized_keys
fi
if grep -qxF '{PUBLIC_KEY}' ~/.ssh/authorized_keys; then
    echo '{MARKER_PRESENT}'
else
    printf '%s\\n' '{PUBLIC_KEY}' >> ~/.ssh/authorized_keys
    grep -qxF '{PUBLIC_KEY}' ~/.ssh/authorized_keys && echo '{MARKER_ADDED}'
fi
"""


def run_ssh(host, user, password):
    """Возвращает (returncode, output_text).

    returncode == 0 ещё не гарантирует добавление ключа — это проверяется
    отдельно по маркеру в output (см. main).
    """
    master_fd, slave_fd = pty.openpty()

    def _make_controlling_tty():
        # Новая сессия + назначение pty управляющим терминалом. Без этого
        # ssh не видит управляющего tty, уходит в графический ssh-askpass
        # и не может получить пароль ("Permission denied").
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    # Чистим окружение, чтобы ssh не пытался использовать внешний askpass
    # вместо нашего pty (на новых OpenSSH это поведение управляется
    # SSH_ASKPASS_REQUIRE).
    env = dict(os.environ)
    env.pop("SSH_ASKPASS", None)
    env.pop("DISPLAY", None)
    env["SSH_ASKPASS_REQUIRE"] = "never"

    proc = subprocess.Popen(
        [
            "ssh",
            "-F", "/dev/null",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            # не даём ssh повторно спрашивать пароль и зависать на неверном:
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "PubkeyAuthentication=no",
            f"{user}@{host}",
            REMOTE_CMD,
        ],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        text=False,
        close_fds=True,
        start_new_session=False,  # сессию создаём сами в preexec_fn
        preexec_fn=_make_controlling_tty,
        env=env,
    )

    os.close(slave_fd)

    password_sent = False
    output = b""
    deadline = time.monotonic() + SESSION_TIMEOUT

    try:
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                output += b"\n[local] SESSION TIMEOUT\n"
                break

            r, _, _ = select.select([master_fd], [], [], 1)

            if r:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""

                if not data:
                    break

                output += data

                # Ищем приглашение во ВСЁМ накопленном буфере, а не в одном
                # куске: иначе при разрыве 'password:' между двумя read()
                # пароль не отправлялся и сессия отваливалась (главный баг).
                if not password_sent and b"password:" in output.lower():
                    os.write(master_fd, (password + "\n").encode())
                    password_sent = True

            if proc.poll() is not None:
                # процесс завершился — дочитываем остаток буфера pty
                break
    finally:
        # финальный дренаж и аккуратное закрытие
        while True:
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            output += data
        os.close(master_fd)

    try:
        rc = proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        rc = proc.wait()

    return rc, output.decode(errors="ignore")


def main():
    try:
        f = open(HOSTS_FILE, encoding="utf-8")
    except OSError as e:
        print(f"Не удалось открыть {HOSTS_FILE}: {e}")
        return 1

    total = ok = added = present = failed = 0

    with f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()

            # Встроенный комментарий: токен, начинающийся с '#', и всё после
            # него отбрасываются (например: "host user pass # комментарий").
            # Пароль с '#' без пробела (Pa#ss) — это один токен, он не
            # начинается с '#' и сохраняется.
            for i, p in enumerate(parts):
                if p.startswith("#"):
                    parts = parts[:i]
                    break

            if len(parts) < 3:
                print(f"Некорректная строка: {line}")
                continue

            host, user, password = parts[:3]
            total += 1
            print(f"\n=== {host} ({user}) ===")

            rc, out = run_ssh(host, user, password)

            # Достоверный признак успеха — маркер от удалённой команды,
            # а не только rc==0.
            if MARKER_ADDED in out:
                print("OK: ключ добавлен")
                ok += 1
                added += 1
            elif MARKER_PRESENT in out:
                print("OK: ключ уже был на хосте")
                ok += 1
                present += 1
            else:
                print(f"СБОЙ (rc={rc}): ключ НЕ подтверждён")
                failed += 1
                if out.strip():
                    print(out.strip())

    print(
        f"\nИтого: {total} хостов | успешно: {ok} "
        f"(добавлено {added}, уже было {present}) | сбоев: {failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
