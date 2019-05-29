from setuptools import setup

with open('README.md') as f:
    long_description = f.read()

version = '0.9.0'

setup(
    name = 'banksync',
    packages = ['banksync'], # this must be the same as the name above
    version = version,
    description = 'A library for manipulating banks of git repositories',
    long_description = long_description,
    long_description_content_type='text/markdown',  # This is important!
    author = 'Jason Harris',
    author_email = 'jason@jasonfharris.com',
    license='MIT',
    url = 'https://github.com/jasonfharris/banksync',
    download_url = 'https://github.com/jasonfharris/banksync/tarball/'+version,
    keywords = ['execute', 'shell', 'system', 'git', 'submodule'],
    classifiers=[
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'Topic :: Software Development :: Version Control',
        'Topic :: Utilities',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.7'
        ],
    install_requires = ['argparse', 'argcomplete', 'sysexecute>=1.1.6', 'configparser'],
    scripts = ['bin/bank', 'bin/banksync']
)