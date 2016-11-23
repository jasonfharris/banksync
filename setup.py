from distutils.core import setup

try:
    import pypandoc
    long_description = pypandoc.convert_file('README.md', 'rst')
except ImportError:
    long_description = open('README.md').read()

setup(
    name = 'banksync',
    packages = ['banksync'], # this must be the same as the name above
    version = '0.7.0',
    description = 'A library for manipulating banks of git repositories',
    long_description = long_description,
    author = 'Jason Harris',
    author_email = 'jason@jasonfharris.com',
    license='MIT',
    url = 'https://github.com/jasonfharris/banksync',
    download_url = 'https://github.com/jasonfharris/banksync/tarball/0.7.0',
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
        'Programming Language :: Python :: 2.7'
        ],
    install_requires = ['argparse', 'argcomplete', 'sysexecute'],
    entry_points = {
        "console_scripts": ['bank = banksync.banksync:main']
        }
)