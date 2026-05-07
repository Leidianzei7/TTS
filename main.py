#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore", message=".*NotOpenSSL.*")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")

from realtime_asr.main import main
main()
