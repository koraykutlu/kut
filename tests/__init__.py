"""Paket olarak çalıştırmada (py -3 -m unittest tests.test_soz) yalıtımı kurar; discover -s tests için her dosya _yalitim'i kendisi içe aktarır."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _yalitim  # noqa: E402,F401
