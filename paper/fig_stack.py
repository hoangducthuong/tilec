from __future__ import print_function
from orphics import maps,io,cosmology,catalogs,stats
from pixell import enmap,reproject
import numpy as np
import os,sys
from soapack import interfaces as sints
import tilec.fg as tfg
import tilec.utils as tutils

random = False
cversion = 'joint'
region = 'deep56'
lmin = 2000

cols = catalogs.load_fits("AdvACT.fits",['RAdeg','DECdeg','SNR'])
ras = cols['RAdeg']
decs = cols['DECdeg']
sns = cols['SNR']


array = "pa3_f150"
#array = "pa3_f090"

freqs = {"pa3_f090":93, "pa3_f150":148}

mask = sints.get_act_mr3_crosslinked_mask(region)
bmask = mask.copy()
bmask[bmask<0.99] = 0
#io.hplot(bmask,"bmask")

dm = sints.ACTmr3(region=mask,calibrated=True)
modlmap = mask.modlmap()
ells = np.arange(0,modlmap.max())
kbeam = dm.get_beam(modlmap, "s15",region,array,sanitize=True)
lbeam = dm.get_beam(ells, "s15",region,array,sanitize=True)
bfile = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_comptony_map_v1.0.0_rc_%s_beam.txt" % (cversion,region,region,cversion)
yfile = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_comptony_map_v1.0.0_rc_%s.fits" % (cversion,region,region,cversion)

bfile2 = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb_map_v1.0.0_rc_%s_beam.txt" % (cversion,region,region,cversion)
yfile2 = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb_map_v1.0.0_rc_%s.fits" % (cversion,region,region,cversion)

bfile3 = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb_deprojects_comptony_map_v1.0.0_rc_%s_beam.txt" % (cversion,region,region,cversion)
yfile3 = os.environ["WORK"] + "/data/depot/tilec/map_v1.0.0_rc_%s_%s/tilec_single_tile_%s_cmb_deprojects_comptony_map_v1.0.0_rc_%s.fits" % (cversion,region,region,cversion)


ls,obells = np.loadtxt(bfile,unpack=True)
obeam = maps.interp(ls,obells)(modlmap)
beam_ratio = kbeam/obeam
beam_ratio[~np.isfinite(beam_ratio)] = 0
kmask = maps.mask_kspace(mask.shape,mask.wcs,lmin=lmin,lmax=30000)
kmap = enmap.fft(dm.get_coadd("s15",region,array,srcfree=True,ncomp=1)[0]*mask)
pwin = tutils.get_pixwin(mask.shape[-2:])
bpfile = "data/"+dm.get_bandpass_file_name(array)
f = tfg.get_mix_bandpassed([bpfile], 'tSZ',ccor_cen_nus=[freqs[array]], ccor_beams=[lbeam])[0]
f2d = maps.interp(ells,f)(modlmap)
#f = tfg.get_mix_bandpassed([bpfile], 'tSZ')#,ccor_cen_nus=[freqs[array]], ccor_beams=[lbeam])[0]
#f2d = f * (modlmap*0 + 1)
filt = kmask/pwin/f2d
filt[~np.isfinite(filt)] = 0
imap = enmap.ifft(kmap*filt).real

ymap = maps.filter_map(enmap.read_map(yfile),beam_ratio*kmask)

smap = enmap.read_map(yfile2)
cmap = enmap.read_map(yfile3)


pix = 60
i = 0
istack = 0
ystack = 0
sstack = 0
cstack = 0

s = stats.Stats()

for ra,dec,sn in zip(ras,decs,sns):

    if random:
        box = mask.box()
        ramin = min(box[0,1],box[1,1])
        ramax = max(box[0,1],box[1,1])
        decmin = min(box[0,0],box[1,0])
        decmax = max(box[0,0],box[1,0])
        ra = np.rad2deg(np.random.uniform(ramin,ramax))
        dec = np.rad2deg(np.random.uniform(decmin,decmax))

    if sn<5:
        continue
        
    mcut = reproject.cutout(bmask, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)
    if mcut is None: 
        continue
    if np.any(mcut)<=0: 
        #print("skipping since in mask")
        continue

    

    icut = reproject.cutout(imap, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)
    ycut = reproject.cutout(ymap, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)
    scut = reproject.cutout(smap, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)
    ccut = reproject.cutout(cmap, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)


    if i==0:
        modrmap = np.rad2deg(icut.modrmap())*60.
        bin_edges = np.arange(0.,10.,1.0)
        binner = stats.bin2D(modrmap,bin_edges)

    cents,i1d = binner.bin(icut)
    cents,y1d = binner.bin(ycut)
    s.add_to_stats("i1d",i1d*1e6)
    s.add_to_stats("y1d",y1d*1e6)

    istack = istack + icut
    ystack = ystack + ycut
    sstack = sstack + scut
    cstack = cstack + ccut
    i += 1
    if i>5000: break

s.get_stats()
print(i)
istack = istack / i * 1e6
ystack = ystack / i * 1e6
sstack = sstack / i
cstack = cstack / i
# io.plot_img(istack,"istack.png",lim=[-5,25])
# io.plot_img(ystack,"ystack.png",lim=[-5,25])
# io.plot_img(sstack,"sstack.png")#,lim=[-5,25])
# io.plot_img(cstack,"cstack.png")#,lim=[-5,25])

_,nwcs = enmap.geometry(pos=(0,0),shape=istack.shape,res=np.deg2rad(0.5/60.))
io.hplot(enmap.enmap(istack,nwcs),"istack",ticks=5,tick_unit='arcmin',grid=True,colorbar=True,color='gray',upgrade=4,min=-5,max=25)
io.hplot(enmap.enmap(ystack,nwcs),"ystack",ticks=5,tick_unit='arcmin',grid=True,colorbar=True,color='gray',upgrade=4,min=-5,max=25)
io.hplot(enmap.enmap(sstack,nwcs),"fig_sstack",ticks=5,tick_unit='arcmin',grid=True,colorbar=True,color='gray',upgrade=4,min=-10,max=30)
io.hplot(enmap.enmap(cstack,nwcs),"fig_cstack",ticks=5,tick_unit='arcmin',grid=True,colorbar=True,color='gray',upgrade=4,min=-10,max=30)



#cents,i1d = binner.bin(istack)
#cents,y1d = binner.bin(ystack)

i1d = s.stats['i1d']['mean']
ei1d = s.stats['i1d']['errmean']

y1d = s.stats['y1d']['mean']
ey1d = s.stats['y1d']['errmean']

pl = io.Plotter(xlabel='$\\theta$ (arcmin)',ylabel='Filtered $Y  (\\times 10^6)$')
pl.add_err(cents,i1d,yerr=ei1d,label="Single frequency ACT_06",ls="none",marker="_",markersize=8,elinewidth=2,mew=2)
pl.add_err(cents+0.1,y1d,yerr=ey1d,label='Compton-Y map',ls="none",marker="x",markersize=8,elinewidth=2,mew=2)
pl.hline(y=0)
pl.done('fig_yprofile.png')

print((i1d-y1d)/y1d*100.)

    
#ycut = reproject.cutout(ymap, ra=np.deg2rad(ra), dec=np.deg2rad(dec),npix=pix)

    

