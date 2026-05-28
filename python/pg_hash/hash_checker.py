from argparse import ArgumentParser as Parser
from lb_hashmap_viewer import HashmapViewer

if __name__ == '__main__':
    parser = Parser()
    parser.add_argument('-f', type=float, default=11)
    args = parser.parse_args()
    f = args.f
    HashmapViewer(f=args.f).view()

