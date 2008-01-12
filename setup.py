"""LabRAD interface for python

LabRAD is a system for quickly and easily building distributed
instrument control and data analysis applications.  pylabrad
provides a python interface to LabRAD.
"""

classifications = """\
Development Status :: 4 - Beta
Environment :: Console
Environment :: Web Environment
Intended Audience :: Science/Research
License :: OSI Approved :: GNU General Public License (GPL)
Operating System :: OS Independent
Programming Language :: Python
Topic :: Scientific/Engineering
"""

from distutils.core import setup

doclines = __doc__.split('\n')

setup(name='pylabrad',
      version='0.9.0',
      author='Matthew Neeley',
      author_email='maffoo@users.sourceforge.net',
      
      url='http://sourceforge.net/projects/pylabrad/',
      download_url='',
      
      description = doclines[0],
      long_description = "\n".join(doclines[2:]),
      classifications = classifications.split('\n'),
      
      requires=['twisted (>=2.5)'],
      provides=['labrad'],
      packages=['labrad', 'labrad.config', 'labrad.pipeline',
	            'labrad.controller', 'labrad.servers',
				'labrad.test', 'labrad.util'],
      package_data={'labrad': ['LICENSE.txt'],
                    'labrad.config': ['*.ini'],
	                'labrad.controller': ['images/*.png']},
      py_modules=['twisted.plugins.labrad_controller',
                  'twisted.plugins.labrad_node'],
      scripts=['labrad_postinstall.py'],
     )