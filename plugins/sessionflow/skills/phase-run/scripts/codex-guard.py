#!/usr/bin/env python3
"""Run Codex behind an input-generation guard. No credential/config copying.

The private socket can atomically compare the user-input epoch and write to the
child PTY. It never clears the composer, suppresses user input, or retries keys.
Terminal reports also cancel reservations conservatively. Screen interpretation
belongs to inject.py, not this transport. Python 3, POSIX, tmux only.
"""
import base64
import fcntl
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import tty
import uuid
from pathlib import Path


def main():
    if not sys.stdin.isatty() or not os.environ.get('TMUX_PANE'):
        raise SystemExit('codex-guard: run from an interactive tmux pane')
    if subprocess.check_output(['codex', '--version'], text=True).strip() != 'codex-cli 0.157.1':
        raise SystemExit('codex-guard: only Codex 0.157.1 is validated; use manual continuation')
    with tempfile.TemporaryDirectory(prefix='pf-', dir='/tmp') as directory:
        path = str(Path(directory) / 'guard.sock')
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(path)
        os.chmod(path, 0o600)
        listener.listen(4)
        nonce = uuid.uuid4().hex
        env = dict(os.environ, PHASEFLOW_GUARD=path)
        args = sys.argv[1:]
        if args[:1] == ['--']:
            args = args[1:]
        if any(arg == '--remote' or arg.startswith('--remote=') for arg in args):
            raise SystemExit('codex-guard: remote/shared TUI sessions are unsupported')
        if '--no-alt-screen' not in args:
            args.append('--no-alt-screen')
        pid, master = pty.fork()
        if pid == 0:
            os.execvpe('codex', ['codex', '--no-daemon', *args], env)
        epoch = 0
        clears = 0
        tail = b''
        lease = None
        old = termios.tcgetattr(0)

        def resize(*_):
            nonlocal epoch
            epoch += 1
            size = fcntl.ioctl(0, termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0))
            fcntl.ioctl(master, termios.TIOCSWINSZ, size)
        resize()
        signal.signal(signal.SIGWINCH, resize)

        def user_input():
            nonlocal epoch, lease
            data = os.read(0, 65536)
            if not data:
                raise EOFError
            epoch += 1
            lease = None
            os.write(master, data)

        try:
            tty.setraw(0)
            while True:
                ready, _, _ = select.select([0, master, listener], [], [], .1)
                # User input always wins over a pending injection RPC.
                if 0 in ready:
                    user_input()
                if master in ready:
                    data = os.read(master, 65536)
                    if not data:
                        break
                    joined = tail + data
                    clears += joined.count(b'\x1b[2J') + joined.count(b'\x1b[3J')
                    tail = joined[-3:]
                    os.write(1, data)
                if listener in ready:
                    conn, _ = listener.accept()
                    with conn:
                        conn.settimeout(.5)
                        try:
                            data = b''
                            while not data.endswith(b'\n') and len(data) < 16384:
                                part = conn.recv(16384)
                                if not part:
                                    raise ValueError('empty request')
                                data += part
                            request = json.loads(data)
                            if select.select([0], [], [], 0)[0]:
                                user_input()
                            op = request.get('op')
                            if op != 'status':
                                if request.get('nonce') != nonce or request.get('epoch') != epoch:
                                    raise ValueError('user input or guard identity changed')
                                if op == 'reserve':
                                    if lease not in (None, request['ticket']):
                                        raise ValueError('another reservation owns this pane')
                                    lease = request['ticket']
                                elif op == 'release':
                                    if lease == request['ticket']:
                                        lease = None
                                elif op == 'send':
                                    if lease != request['ticket']:
                                        raise ValueError('reservation lost')
                                    payload = base64.b64decode(request['data'], validate=True)
                                    if len(payload) > 4096:
                                        raise ValueError('input too large')
                                    os.write(master, payload)
                                else:
                                    raise ValueError('unknown operation')
                            response = dict(ok=True, nonce=nonce, epoch=epoch, clears=clears,
                                            pane=os.environ['TMUX_PANE'], pid=os.getpid(),
                                            server_socket=os.path.realpath(os.environ['TMUX'].rsplit(',', 2)[0]))
                        except (ValueError, KeyError, socket.timeout) as error:
                            response = dict(ok=False, error=str(error))
                        try:
                            conn.sendall(json.dumps(response).encode() + b'\n')
                        except OSError:
                            pass  # A timed-out worker must not terminate the user's TUI.
        except (OSError, EOFError, KeyboardInterrupt):
            pass
        finally:
            termios.tcsetattr(0, termios.TCSADRAIN, old)
            os.close(master)
            try:
                os.kill(pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)


if __name__ == '__main__':
    main()
