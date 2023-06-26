from pathlib import Path
from setuptools import setup


def readme():
    this_directory = Path(__file__).parent.resolve()
    with open(this_directory / 'README.md', encoding='utf-8') as f:
        return f.read()


setup(
    name='pytr',
    version='0.1.5',
    description='Use TradeRepublic in terminal',
    long_description=readme(),
    long_description_content_type='text/markdown',
    url='https://gitlab.com/marzzzello/pytr/',
    author='marzzzello',
    author_email='853485-marzzzello@users.noreply.gitlab.com',
    license='MIT',
    packages=['pytr'],
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'pytr = pytr.main:main',
        ],
    },
    #  scripts=['traderep'],
    # install_requires=['py_tr'],
    install_requires=[
        'certifi',
        'coloredlogs',
        'ecdsa',
        'packaging',
        'pathvalidate',
        'pygments',
        'requests_futures',
        'shtab',
        'websockets>=10.1',
        'wxpython>=4.1.0',
        'Pillow>=4.3.0',
        'psutil>=5.4.2',
        'colored>=1.3.93',
        'pygtrie>=2.3.3',
        're-wx>=0.0.2',
        'typing-extensions',
        'mypy-extensions==0.4.3',
        'Gooey',
    ],
    classifiers=[
        "License :: OSI Approved :: MIT License",
        'Programming Language :: Python :: 3 :: Only',
        "Operating System :: OS Independent",
        'Development Status :: 3 - Alpha',
        "Topic :: Office/Business :: Financial",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
    zip_safe=False,
)
