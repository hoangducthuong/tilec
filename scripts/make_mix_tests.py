from tilec import fg as tfg
import numpy as np
import glob
import pickle

version = "MM_20200307"

fdict = tfg.get_test_fdict()
pickle.dump(fdict,open("%s_fdict.pkl" % version,'wb'), protocol=2)
