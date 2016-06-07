#!/usr/bin/env python

import os
import sys
import playground
from pox.boot import boot

sys.path.append(os.path.expanduser('./playground'))

if __name__ == '__main__':
    boot()
