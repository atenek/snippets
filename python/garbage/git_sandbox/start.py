import sys
import git_helper as git_helper

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    print(git_helper.log(10, path))
