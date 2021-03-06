from __future__ import print_function
import matplotlib
matplotlib.use('Agg')
from orphics import maps,io,cosmology,mpi
from pixell import enmap
import numpy as np
import os,sys,shutil
from datetime import datetime
from actsims import noise as actnoise
from actsims.util import seed_tracker
from soapack import interfaces as sints
from enlib import bench
from tilec import pipeline,utils as tutils


pdefaults = io.config_from_yaml("input/cov_defaults.yml")['cov']

import argparse
# Parse command line
parser = argparse.ArgumentParser(description='Do a thing.')
parser.add_argument("version", type=str,help='Version name.')
parser.add_argument("region", type=str,help='Region name.')
parser.add_argument("arrays", type=str,help='Comma separated list of array names. Array names map to a data specification in data.yml')
parser.add_argument("solutions", type=str,help='Comma separated list of solutions. Each solution is of the form x-y-... where x is solved for and the optionally provided y-,... are deprojected. The x can belong to any of CMB,tSZ and y,z,... can belong to any of CMB,tSZ,CIB.')
parser.add_argument("beams", type=str,help='Comma separated list of beams. Each beam is either a float for FWHM in arcminutes or the name of an array whose beam will be used.')
parser.add_argument("beams_planck", type=str,help='Comma separated list of beams. Each beam is either a float for FWHM in arcminutes or the name of an array whose beam will be used.')
parser.add_argument("-N", "--nsims",     type=int,  default=1,help="A description.")
parser.add_argument("--start-index",     type=int,  default=0,help="A description.")
parser.add_argument("--skip-inpainting", action='store_true',help='Do not inpaint.')
parser.add_argument("--use-cached-sims", action='store_true',help='Use cached sims.')
parser.add_argument("--fft-beam", action='store_true',help='Apply the beam and healpix-pixwin with FFTs instead of SHTs.')
parser.add_argument("--exclude-tsz", action='store_true',help='Do not include tsz.')
parser.add_argument("--save-all", action='store_true',help='Do not delete anything intermediate.')
parser.add_argument("--isotropize", action='store_true',help='Isotropize at ilc step.')
parser.add_argument("--isotropic-override", action='store_true',help='Isotropize at cov step.')
parser.add_argument("--skip-fg", action='store_true',help='Skip fg res.')
parser.add_argument("--skip-only", action='store_true',help='Skip ACT/Planck-only.')
parser.add_argument("--save-extra", action='store_true',help='Save extra.')
parser.add_argument("--do-weights", action='store_true',help='Do weights.')
parser.add_argument("--theory",     type=str,  default="none",help="A description.")
parser.add_argument("--fg-res-version", type=str,help='Version name for residual foreground powers.',default='fgfit_v2')
parser.add_argument("--sim-version", type=str,help='Region name.',default='v6.2.0_calibrated_mask_version_padded_v1')
parser.add_argument("--mask-version", type=str,  default="padded_v1",help='Mask version')
parser.add_argument("-o", "--overwrite", action='store_true',help='Ignore existing version directory.')
parser.add_argument("-m", "--memory-intensive", action='store_true',help='Do not save FFTs to scratch disk. Can be faster, but very memory intensive.')
parser.add_argument("--uncalibrated", action='store_true',help='Do not use calibration factors.')
parser.add_argument("--signal-bin-width",     type=int,  default=pdefaults['signal_bin_width'],help="A description.")
parser.add_argument("--signal-interp-order",     type=int,  default=pdefaults['signal_interp_order'],help="A description.")
parser.add_argument("--delta-ell",     type=int,  default=pdefaults['delta_ell'],help="A description.")
parser.add_argument("--set-id",     type=int,  default=0,help="Sim set id.")
parser.add_argument("--rfit-bin-width",     type=int,  default=pdefaults['rfit_bin_width'],help="A description.")
parser.add_argument("--rfit-wnoise-width",     type=int,  default=pdefaults['rfit_wnoise_width'],help="A description.")
parser.add_argument("--rfit-lmin",     type=int,  default=pdefaults['rfit_lmin'],help="A description.")
parser.add_argument("--chunk-size",     type=int,  default=5000000,help="Chunk size.")
parser.add_argument("--maxval",     type=float,  default=700000,help="Maxval for covmat.")
parser.add_argument("--beam-version", type=str,  default=None,help='Mask version')
parser.add_argument("-e", "--effective-freq", action='store_true',help='Ignore bandpass files and use effective frequency.')
parser.add_argument("--unsanitized-beam", action='store_true',help='Do not sanitize beam.')
parser.add_argument("--no-act-color-correction", action='store_true',help='Do not color correct ACT arrays in a scale dependent way.')
parser.add_argument("--ccor-exp",     type=float,  default=-1,help="ccor exp.")
args = parser.parse_args()

print("Command line arguments are %s." % args)
tutils.validate_args(args.solutions,args.beams)
tutils.validate_args(args.solutions,args.beams_planck)

# Prepare act-only and planck-only jobs
qids = args.arrays.split(',')
act_arrays = [] ; planck_arrays = []
for qid in qids:
    if tutils.is_planck(qid): 
        planck_arrays.append(qid)
    else: 
        act_arrays.append(qid)
do_act_only = (len(act_arrays)>0) and not(args.skip_only)
do_planck_only = (len(planck_arrays)>0) and not(args.skip_only)
act_arrays = ','.join(act_arrays)
planck_arrays = ','.join(planck_arrays)
print("Starting simulation for arrays %s of which %s are ACT and %s are Planck." % (args.arrays,act_arrays,planck_arrays))


# Generate each ACT and Planck sim and store kdiffs,kcoadd in memory

set_id = args.set_id
bandpasses = not(args.effective_freq)
gconfig = io.config_from_yaml("input/data.yml")
mask = sints.get_act_mr3_crosslinked_mask(args.region,
                                          version=args.mask_version,
                                          kind='binary_apod')
shape,wcs = mask.shape,mask.wcs
Ny,Nx = shape
modlmap = enmap.modlmap(shape,wcs)

ngen = {}
ngen['act_mr3'] = actnoise.NoiseGen(args.sim_version,model="act_mr3",extract_region=mask,ncache=0,verbose=True)
ngen['planck_hybrid'] = actnoise.NoiseGen(args.sim_version,model="planck_hybrid",extract_region=mask,ncache=0,verbose=True)


arrays = args.arrays.split(',')
narrays = len(arrays)
nsims = args.nsims

jsim = pipeline.JointSim(arrays,args.fg_res_version+"_"+args.region,
                         bandpassed=bandpasses,no_act_color_correction=args.no_act_color_correction,
                         ccor_exp=args.ccor_exp)

comm,rank,my_tasks = mpi.distribute(nsims)

for task in my_tasks:
    sim_index = task + args.start_index

    print("Rank %d starting task %d at %s..." % (rank,task,str(datetime.now())))

    ind_str = str(set_id).zfill(2)+"_"+str(sim_index).zfill(4)
    sim_version = "%s_%s" % (args.version,ind_str)
    scratch = tutils.get_scratch_path(sim_version,args.region)
    try: 
        os.makedirs(scratch)
    except: 
        pass
    """
    MAKE SIMS
    """
    jsim.update_signal_index(sim_index,set_idx=set_id)

    pa3_cache = {} # This assumes there are at most 2 pa3 arrays in the input
    sim_splits = []
    for aindex in range(narrays):
        qid = arrays[aindex]
        fname = tutils.get_temp_split_fname(qid,args.region,sim_version)

        if not(args.use_cached_sims):
            dmname = sints.arrays(qid,'data_model')
            dm = sints.models[dmname](region=mask,calibrated=not(args.uncalibrated))
            patch = args.region

            if dm.name=='act_mr3':
                season,array1,array2 = sints.arrays(qid,'season'),sints.arrays(qid,'array'),sints.arrays(qid,'freq')
                arrayname = array1 + "_" + array2
            elif dm.name=='planck_hybrid':
                season,arrayname = None,sints.arrays(qid,'freq')


            with bench.show("signal"):
                # (npol,Ny,Nx)
                signal = jsim.compute_map(mask.shape,mask.wcs,qid,
                                          include_cmb=True,include_tsz=not(args.exclude_tsz),
                                          include_fgres=not(args.skip_fg),sht_beam=not(args.fft_beam))


            # Special treatment for pa3
            farray = arrayname.split('_')[0]
            if farray=='pa3':
                try:
                    noise,ivars = pa3_cache[arrayname]
                    genmap = False
                except:
                    genmap = True
            else:
                genmap = True

            if genmap:
                # (ncomp,nsplits,npol,Ny,Nx)
                noise_seed = seed_tracker.get_noise_seed(set_id, sim_index, ngen[dmname].dm, season, patch, farray, None)
                fnoise,fivars = ngen[dmname].generate_sim(season=season,patch=patch,array=farray,seed=noise_seed,apply_ivar=False)
                print(fnoise.shape,fivars.shape)
                if farray=='pa3': 
                    ind150 = dm.array_freqs['pa3'].index('pa3_f150')
                    ind090 = dm.array_freqs['pa3'].index('pa3_f090')
                    pa3_cache['pa3_f150'] = (fnoise[ind150].copy(),fivars[ind150].copy())
                    pa3_cache['pa3_f090'] = (fnoise[ind090].copy(),fivars[ind090].copy())
                    ind = dm.array_freqs['pa3'].index(arrayname)
                else:
                    ind = 0
                noise = fnoise[ind]
                ivars = fivars[ind]

            splits = actnoise.apply_ivar_window(signal[None,None]+noise[None],ivars[None])
            assert splits.shape[0]==1
            enmap.write_map(fname,splits[0])

        sim_splits.append(fname)

    
    """
    k-space coadd
    """



    """
    SAVE COV
    """
    print("Beginning covariance calculation...")
    with bench.show("sim cov"):
        pipeline.build_and_save_cov(args.arrays,args.region,sim_version,args.mask_version,
                                    args.signal_bin_width,args.signal_interp_order,args.delta_ell,
                                    args.rfit_wnoise_width,args.rfit_lmin,
                                    args.overwrite,args.memory_intensive,args.uncalibrated,
                                    sim_splits=sim_splits,skip_inpainting=args.skip_inpainting,
                                    theory_signal=args.theory,unsanitized_beam=args.unsanitized_beam,
                                    save_all=args.save_all,plot_inpaint=False,save_extra=args.save_extra,
                                    isotropic_override=args.isotropic_override)



    print("Done with cov.")

    """
    SAVE ILC
    """
    print("Starting joint ILC")
    ilc_version = "map_joint_%s_%s" % (args.version,ind_str)
    with bench.show("sim ilc"):
        pipeline.build_and_save_ilc(args.arrays,args.region,ilc_version,sim_version,args.beam_version,
                                    args.solutions,args.beams,args.chunk_size,
                                    args.effective_freq,args.overwrite,args.maxval,
                                    unsanitized_beam=args.unsanitized_beam,do_weights=args.do_weights,
                                    no_act_color_correction=args.no_act_color_correction,ccor_exp=args.ccor_exp,
                                    isotropize=args.isotropize)


    if do_act_only:
        print("Starting ACT-only ILC")
        ilc_version = "map_act_only_%s_%s" % (args.version,ind_str)
        with bench.show("sim ilc"):
            pipeline.build_and_save_ilc(act_arrays,args.region,ilc_version,sim_version,args.beam_version,
                                        args.solutions,args.beams,args.chunk_size,
                                        args.effective_freq,args.overwrite,args.maxval,
                                        unsanitized_beam=args.unsanitized_beam,do_weights=args.do_weights,
                                        no_act_color_correction=args.no_act_color_correction,ccor_exp=args.ccor_exp,
                                        isotropize=args.isotropize)


    if do_planck_only:
        print("Starting Planck-only ILC")
        ilc_version = "map_planck_only_%s_%s" % (args.version,ind_str)
        with bench.show("sim ilc"):
            pipeline.build_and_save_ilc(planck_arrays,args.region,ilc_version,sim_version,args.beam_version,
                                        args.solutions,args.beams_planck,args.chunk_size,
                                        args.effective_freq,args.overwrite,args.maxval,
                                        unsanitized_beam=args.unsanitized_beam,do_weights=args.do_weights,
                                        no_act_color_correction=args.no_act_color_correction,ccor_exp=args.ccor_exp,
                                        isotropize=args.isotropize)





    savepath = tutils.get_save_path(sim_version,args.region)
    if not(args.save_all): shutil.rmtree(savepath)
    print("Rank %d done with task %d at %s." % (rank,task,str(datetime.now())))
