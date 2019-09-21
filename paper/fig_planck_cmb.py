from __future__ import print_function
from orphics import maps,io,cosmology,stats
from pixell import enmap,reproject
import numpy as np
import os,sys
import healpy as hp
from soapack import interfaces as sints
import tilec.fg as tfg
import tilec.utils as tutils

cversion = 'joint'
redo = True
fwhm = 5.
invbeam = lambda x: np.piecewise(x, [x<1,x>=1], [lambda y: y*0 , lambda y: 1./maps.gauss_beam(y,fwhm)])

dfwhm = 0.0001



for method,methodp in zip(['','_deprojects_comptony'],['sz','nosz']):
    pl = io.Plotter(xyscale='loglog',xlabel='$\\ell$',ylabel='$D_{\\ell}$',scalefn = lambda x: x**2./2./np.pi)
    for col,region in zip(['red','blue'],['deep56','boss']):

        if redo:
            mask = sints.get_act_mr3_crosslinked_mask(region)
            shape,wcs = mask.shape,mask.wcs

            bfile = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb%s_map_v1.0.0_rc_%s_beam.txt" % (cversion,region,region,method,cversion)
            yfile = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb%s_map_v1.0.0_rc_%s.fits" % (cversion,region,region,method,cversion)
            w2 = np.mean(mask**2.)

            als,bells = np.loadtxt(bfile,unpack=True)
            imap = enmap.read_map(yfile)
            modlmap = mask.modlmap()
            bin_edges = np.arange(20,6000,20)

            binner = stats.bin2D(modlmap,bin_edges)
            kmap = enmap.fft(imap,normalize='phys')/maps.interp(als,bells)(modlmap)*maps.gauss_beam(modlmap,dfwhm)
            kmap[~np.isfinite(kmap)] = 0
            p2d = (kmap*kmap.conj()).real / w2

            cents,p1d = binner.bin(p2d)
            io.save_cols(os.environ['WORK']+"/cpower_tilec_%s_%s.txt" % (region,method), (cents,p1d))
        else:
            cents,p1d = np.loadtxt("cpower_tilec_%s_%s.txt" % (region,method), unpack=True)

        pl.add(cents,p1d,color=col,label='This work (%s)' % region)


        if redo:

            bin_edges = np.arange(20,3000,20)
            binner = stats.bin2D(modlmap,bin_edges)

            if methodp=='sz':
                ppath = "/scratch/r/rbond/msyriac/data/planck/data/pr2/"
                alm = hp.read_alm(ppath + 'COM_CMB_IQU-smica-field-Int_2048_R2.01_full_alm.fits',hdu=1) * 1e6
                szlab = "SMICA (PR2)"
            elif methodp=='nosz':
                ppath = "/scratch/r/rbond/msyriac/data/planck/data/pr3/"
                alm = hp.read_alm(ppath + 'COM_CMB_IQU-smica-nosz_2048_R3.00_full_alm.fits',hdu=1) * 1e6
                szlab = "SMICA-nosz (PR3)"
                
            imap = reproject.enmap_from_healpix(alm, shape, wcs, ncomp=1, unit=1, lmax=6000,
                                                rot="gal,equ", first=0, is_alm=True, return_alm=False) * mask
            #io.hplot(enmap.downgrade(imap,4),"ymap_%s_%s" % (region,method),grid=True,color='gray')

            nside = 2048
            pixwin = hp.pixwin(nside=nside,pol=False)
            pls = np.arange(len(pixwin))
            pwin = maps.interp(pls,pixwin)(modlmap)


            kmap = enmap.fft(imap,normalize='phys')/maps.gauss_beam(modlmap,fwhm)*maps.gauss_beam(modlmap,dfwhm)/pwin
            kmap[~np.isfinite(kmap)] = 0 
            p2d = (kmap*kmap.conj()).real / w2

            cents,p1d = binner.bin(p2d)
            io.save_cols(os.environ['WORK']+"/cpower_planck_%s_%s.txt" % (region,method), (cents,p1d))
        else:
             cents,p1d  = np.loadtxt("cpower_planck_%s_%s.txt" % (region,method),unpack=True)
        pl.add(cents,p1d,color=col,label='Planck %s %s' % (szlab,region),ls="--")


    pl.done(os.environ['WORK']+"/fig_cmb_power%s.png" % method)