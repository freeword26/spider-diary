from setuptools import setup, find_packages

setup(
    name="spider-diary",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "psutil>=5.9.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "spider-diary=spider_diary.cli.main:main",
        ],
    },
)
