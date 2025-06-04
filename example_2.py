'''


NOTES:

For more sophisticated A&M style

'''

import numpy as np # for efficient array numerical operations 
import matplotlib.pylab as plt # for plotting
import seaborn as sns # for good colourblind colour scheme
import yaml # for reading in the input parameter YAML file

from atm_module import hypsometric, visc_mixture, v_f_sat_adj

from T_p_Guillot_2010 import Guillot_T_p # Import function for Guillot 2010 semi-grey profile
from T_p_Parmentier_2015 import Parmentier_T_p # Import function for Parmentier & Guillot 2015 picket-fence profile

from tracer_sat_adj import tracer_sat_adj
from exp_vert_adv import exp_vert_adv
from exp_vert_diff import exp_vert_diff

R = 8.31446261815324e7
kb = 1.380649e-16
amu = 1.66053906892e-24

# Open parameter YAML file and read parameters for A&M profile
with open('parameters.yaml', 'r') as file:
  param = yaml.safe_load(file)['tracer_saturation_adjustment']

# Now extract the parameters from the YAML file into local variables

# Give number of layers in 1D atmosphere - number of levels is nlay + 1
nlay = param['nlay']
nlev = nlay + 1

mu_z = param['mu_z']
Tirr = param['Tirr']
Tint = param['Tint']
k_v =  param['k_v']
k_ir = param['k_ir']
met = param['met']
grav = param['grav']
kappa = param['kappa']

# Get top and bottom pressure layers in bar - convert to dyne
ptop = param['ptop'] * 1e6
pbot = param['pbot'] * 1e6

# Get pressure at levels (edges) - assume log-spaced
pe = np.logspace(np.log10(ptop),np.log10(pbot),nlev)

# Get pressure at layers using level spacing
pl = np.zeros(nlay)
pl[:] = (pe[1:] - pe[0:-1])/np.log(pe[1:]/pe[0:-1])
 

# Kzz profile - here we assume constant but a 1D array for easy change to
# non-constant or some function with some editing
# A&M (2001) use a convective heat flux mixing length theory prescription
Kzz = np.zeros(nlay)
Kzz[:] = param['Kzz']
# Example change - use expression from Parmentier et al. (2013):
#Kzz[:] = 5e8/np.sqrt(pl[:]*1e-6)

# We do the same for molecular weight of the atmosphere 
# Can be changed to varying with height/pressure
mu = np.zeros(nlay)
mu[:] = param['mu']

# Get 1D analytical temperature pressure profile at layers
Tl = np.zeros(nlay)
if (param['Guillot'] == True):
  Tl[:] = Guillot_T_p(nlay, pbot, pl, k_v, k_ir, Tint, mu_z, Tirr, grav)
elif (param['Parmentier'] == True):
  Tl[:] = Parmentier_T_p()
else:
  print('Invalid T structure selection')
  quit()

# Atmosphere mass density
rho = np.zeros(nlay)
rho[:] = (pl[:]*mu[:]*amu)/(kb * Tl[:])

# Atmosphere thermal velocity
cT = np.zeros(nlay)
cT[:] = np.sqrt((2.0 * kb * Tl[:]) / (mu[:] * amu))

# Find the altitude grid and scale heights at levels and layers using the hypsometric equation
alte = np.zeros(nlev)
alte, Hp = hypsometric(nlev, Tl, pe, mu, grav)
altl = (alte[0:-1] + alte[1:])/2.0

# Volume mixing ratio of condensate vapour at lower boundary
# Deep abyssal mixing ratio (assume infinite supply at constant value)
bg_sp = param['bg_sp']
bg_VMR = param['bg_VMR']
bg_mw = param['bg_mw']
bg_d = param['bg_d']
bg_LJ = param['bg_LJ']
nbg = len(bg_sp)

# Find dynamical viscosity of each layer given a background gas mixture
eta = np.zeros(nlay)
for k in range(nlay):
  eta[k] = visc_mixture(Tl[k], nbg, bg_VMR, bg_mw, bg_d, bg_LJ)

# Find mean free path of each layer
mfp = np.zeros(nlay)
mfp[:] = (2.0*eta[:]/rho[:]) * np.sqrt((np.pi * mu[:])/(8.0*R*Tl[:]))

cld_sp = param['cld_sp']
cld_mw = param['cld_mw']
r_m =  param['cld_r_m']
r_m = np.array(r_m)
r_m[:] = r_m[:] * 1e-4
sig =  param['cld_sig']
rho_d = param['rho_d']
tau_cond = param['cld_tau_c']

vap_mw =  param['vap_mw']
vap_VMR = param['vap_VMR']

ncld = len(cld_sp)

# Lower boundary conditions for vapour and condensate
q_v_bot = np.zeros(ncld)
for n in range(ncld):
  q_v_bot[n] = vap_VMR[n] * vap_mw[n]/mu[-1]

q_c_bot = np.zeros(ncld)
q_c_bot[:] = 1e-30

n_step = param['n_step']
t_step = param['t_step']

q_v = np.zeros((nlay,ncld))
q_c = np.zeros((nlay,ncld))
q_s = np.zeros((nlay,ncld))
N_c = np.zeros((nlay,ncld))
v_f = np.zeros((nlay,ncld))

# Being timestepping loop for n_step
t_now = 0.0
for t in range(n_step):


  # Perform saturation adjustment for each tracer in each layer
  for n in range(ncld):
    q_v[:,n], q_c[:,n], q_s[:,n] = \
      tracer_sat_adj(nlay, t_step, vap_VMR[n], vap_mw[n], cld_sp[n], rho_d[n], cld_mw[n], Tl, pl, rho, met, tau_cond[n], q_v[:,n], q_c[:,n])

  # Calculate vertical settling velocity for each tracer in each layer
  for n in range(ncld):
    v_f[:,n] = \
      v_f_sat_adj(nlay, r_m[n], sig[n], grav, rho_d[n], rho, eta, mfp, cT)

  # Advect condensate tracer (downwards) - give condensate boundary conditions
  for n in range(ncld):
    q_c[:,n] = \
       exp_vert_adv(t_step, nlay, v_f[:,n], rho, alte, altl, q_c[:,n], q_c_bot[n])

  # Diffuse vapour and condensate tracer (upward and downward) - give vapour and condensate boundary conditions
  for n in range(ncld):
    q_v[:,n] = \
      exp_vert_diff(t_step, nlay, Kzz, rho, alte, altl, q_v[:,n], q_v_bot[n])

  for n in range(ncld):
    q_c[:,n] = \
      exp_vert_diff(t_step, nlay, Kzz, rho, alte, altl, q_c[:,n], q_c_bot[n])

  # Limit values to a maximum
  q_c[:,:] = np.maximum(q_c[:,:], 1e-30)
  q_v[:,:] = np.maximum(q_v[:,:], 1e-30)

  t_now += t_step

  print(t, t_now)

# After time-stepping, find N_c at each layer
for n in range(ncld):
  N_c[:,n] = (3.0 * q_c[:,n] * rho[:])/(4.0*np.pi*rho_d[n]*r_m[n]**3) \
    * np.exp(-9.0/2.0 * np.log(sig[n])**2)

fig = plt.figure() # Start figure 

colour = sns.color_palette('colorblind') # Decent colourblind wheel (10 colours)

plt.plot(Tl,pl/1e6,c=colour[0],ls='solid',lw=2,label=r'T-p')
plt.xlabel(r'$T$ [K]',fontsize=16)
plt.ylabel(r'$p$ [bar]',fontsize=16)
plt.tick_params(axis='both',which='major',labelsize=14)
plt.legend()
plt.yscale('log')
plt.gca().invert_yaxis()
plt.tight_layout(pad=1.05, h_pad=None, w_pad=None, rect=None)

plt.savefig('example_2_T_p.png',dpi=300,bbox_inches='tight')

fig = plt.figure() # Start figure 

colour = sns.color_palette('colorblind') # Decent colourblind wheel (10 colours)

for n in range(ncld):
  if (n == 0):
    plt.plot(q_v[:,n],pl/1e6,c=colour[n],ls='solid',lw=2,label=r'$q_{\rm v}$')
    plt.plot(q_c[:,n],pl/1e6,c=colour[n],ls='dashed',lw=2,label=r'$q_{\rm c}$')
    plt.plot(q_s[:,n],pl/1e6,c=colour[n],ls='dotted',lw=2,label=r'$q_{\rm s}$')
  else:
    plt.plot(q_v[:,n],pl/1e6,c=colour[n],ls='solid',lw=2)
    plt.plot(q_c[:,n],pl/1e6,c=colour[n],ls='dashed',lw=2)
    plt.plot(q_s[:,n],pl/1e6,c=colour[n],ls='dotted',lw=2)    

plt.xlabel(r'$q$ [g g$^{-1}$]',fontsize=16)
plt.ylabel(r'$p$ [bar]',fontsize=16)
plt.tick_params(axis='both',which='major',labelsize=14)
plt.legend()
plt.xscale('log')
plt.yscale('log')
plt.gca().invert_yaxis()
plt.tight_layout(pad=1.05, h_pad=None, w_pad=None, rect=None)

plt.savefig('example_2_q.png',dpi=300,bbox_inches='tight')

fig = plt.figure() # Start figure 

colour = sns.color_palette('colorblind') # Decent colourblind wheel (10 colours)

for n in range(ncld):
  if (n == 0):
    plt.plot(N_c[:,n],pl/1e6,c=colour[n],ls='solid',lw=2,label=r'$N_{\rm c}$')
  else:
    plt.plot(N_c[:,n],pl/1e6,c=colour[n],ls='solid',lw=2)
plt.xlabel(r'$N_{\rm c}$ [cm$^{-3}$]',fontsize=16)
plt.ylabel(r'$p$ [bar]',fontsize=16)
plt.tick_params(axis='both',which='major',labelsize=14)
plt.legend()
plt.xscale('log')
plt.yscale('log')
plt.gca().invert_yaxis()
plt.tight_layout(pad=1.05, h_pad=None, w_pad=None, rect=None)

plt.savefig('example_2_N_c.png',dpi=300,bbox_inches='tight')


fig = plt.figure() # Start figure 

colour = sns.color_palette('colorblind') # Decent colourblind wheel (10 colours)

for n in range(ncld):
  if (n == 0):
    plt.plot(v_f[:,n],pl/1e6,c=colour[n],ls='solid',lw=2,label=r'$v{\rm f}$')
  else:
    plt.plot(v_f[:,n],pl/1e6,c=colour[n],ls='solid',lw=2)
plt.xlabel(r'$v_{\rm f}$ [cm s$^{-1}$]',fontsize=16)
plt.ylabel(r'$p$ [bar]',fontsize=16)
plt.tick_params(axis='both',which='major',labelsize=14)
plt.legend()
plt.xscale('log')
plt.yscale('log')
plt.gca().invert_yaxis()
plt.tight_layout(pad=1.05, h_pad=None, w_pad=None, rect=None)

plt.savefig('example_2_v_f.png',dpi=300,bbox_inches='tight')

plt.show()