import curses
import sys
from argparse import ArgumentParser as Parser
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.player_tui import Cli
from lib.player_pg import HashMapper

if __name__ == '__main__':
    parser = Parser()

    parser.add_argument('-m', type=int, default=48, choices=HashMapper.MODES)
    parser.add_argument('-f', type=float, default=11)

    args = parser.parse_args()

    if args.f <= 0:
        parser.error(f"f = {args.f} < 0")

    if args.m not in HashMapper.MODES:
        parser.error(f"mode: {args.m} not in {HashMapper.MODES}")

    hm = HashMapper(mode=args.m, pos=(0, 398), f=args.f)

    def fn(f):
        f()
        hm.stop_event.set()

    pt = threading.Thread(target=fn, args=(lambda: hm.play_src(f=args.f),), daemon=True, name='player')
    pt.start()

    fn(lambda: curses.wrapper(lambda x: Cli(x, args.m).run(hm.state_ref, hm.f_ref, hm.cmds, hm.stop_event)))
    pt.join()
